#!/usr/bin/env python3.11
"""
Full Deploy Workflow

Apply changeset → Build ISO → Deploy to Proxmox in one command.
This handles the complete deployment pipeline to Proxmox VMs.
"""

import sys
import subprocess
import argparse
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import ROOT, log, warn, error, info, run_command, load_config, get_remote_config, scp, ssh, list_newest_changesets

def full_deploy_workflow(changeset_name, force=False, build_only=False, iso_only=False, use_iso=False):
    """Execute the full deployment workflow: changeset → IMG/ISO → Proxmox"""
    
    build_type = "ISO" if use_iso else "IMG"
    log(f"Starting full deployment workflow for changeset: {changeset_name} (building {build_type})")
    
    if iso_only or build_only:
        mode_desc = "ISO-only" if iso_only else "Build-only"
        log(f"{mode_desc} mode: Skipping fetch, apply, and validation steps")
        # Skip directly to Step 2: Build ISO/IMG
    else:
        # Step 1: Apply changeset
        log("Step 1/3: Applying changeset...")
        apply_script = ROOT / "scripts" / "apply-changeset.py"
        changeset_path = ROOT / "config" / "changesets" / f"{changeset_name}.yaml"
        
        if not changeset_path.exists():
            error(f"Changeset not found: {changeset_path}")
            # Show recent changesets to help user choose
            recent = list_newest_changesets(5)
            if recent:
                error(f"Recent changesets (try one of these): {', '.join(recent)}")
            return False
        
        cmd = [sys.executable, str(apply_script), str(changeset_name)]
        try:
            result = subprocess.run(cmd, cwd=ROOT, check=True)
            log("✓ Changeset applied successfully")
        except subprocess.CalledProcessError as e:
            error(f"Failed to apply changeset: {e}")
            return False
    
    # Step 2: Build IMG or ISO
    step_num = "1/2" if iso_only else "2/3"
    log(f"Step {step_num}: Building OpenCore {build_type}...")
    
    if use_iso:
        build_script = ROOT / "scripts" / "build-iso.py"
    else:
        build_script = ROOT / "scripts" / "build-img.py"
    
    cmd = [sys.executable, str(build_script), changeset_name]

    if force:
        cmd.append("--force")
    
    try:
        result = subprocess.run(cmd, cwd=ROOT, check=True)
        log(f"✓ {build_type} built successfully")
    except subprocess.CalledProcessError as e:
        error(f"Failed to build {build_type}: {e}")
        return False
    
    if build_only:
        log("Build-only mode: Skipping deployment")
        info(f"{build_type} is ready for manual deployment")
        return True
    
    # Step 3: Deploy to Proxmox
    step_num = "2/2" if iso_only else "3/3"
    log(f"Step {step_num}: Deploying to Proxmox...")
    
    try:
        # Load environment configuration
        load_config()
        config = get_remote_config()
        
        vmid = config['vmid']
        workdir = config['workdir']
        
        log(f"Deploying to VM {vmid} on Proxmox")
        
        if use_iso:
            return deploy_iso(changeset_name, vmid, config)
        else:
            return deploy_img(changeset_name, vmid, config)
        
    except Exception as e:
        error(f"Deployment failed: {e}")
        return False
    
    log("🎉 Full deployment workflow completed successfully!")
    info(f"VM {vmid} should now be booting with OpenCore")
    info("You can access the VM console via Proxmox web interface")
    
    return True

def deploy_img(changeset_name, vmid, config):
    """Deploy IMG file to Proxmox VM via SSH using pvesm alloc"""
    try:
        # Check that IMG file exists
        img_filename = f'opencore-{changeset_name}.img'
        img_path = ROOT / 'out' / img_filename
        
        if not img_path.exists():
            error(f"IMG file not found: {img_path}")
            error("Please build the IMG first using build-img.py")
            return False
            
        log(f"Found IMG file: {img_path}")
        
        # Copy IMG to /tmp on remote host
        temp_img_path = f"/tmp/{img_filename}"
        info(f"Copying IMG to {config['host']}:{temp_img_path}")
        
        if not scp(img_path, temp_img_path):
            error("Failed to copy IMG to remote host")
            return False
            
        log("IMG copied to temporary location")
        
        # Deploy to VM via SSH
        info(f"Deploying IMG to VM {vmid}")
        
        # Stop the VM
        info(f"Stopping VM {vmid}")
        if not ssh(f"qm stop {vmid}"):
            warn(f"Could not stop VM {vmid} (may already be stopped)")
        
        try:
            # Create disk name (strip .img and add .raw)
            disk_name = f"opencore-{changeset_name}.raw"
            
            # Use pvesm alloc to create/ensure managed disk exists
            log(f"Allocating managed disk: {disk_name}")
            result = subprocess.run(
                ['ssh', f"root@{config['host']}", f"pvesm alloc local {vmid} {disk_name} 150M --format raw"],
                capture_output=True, text=True, check=False
            )
            
            if result.returncode == 0:
                # Parse the output to get the disk path
                output_lines = result.stdout.strip().split('\n')
                disk_path = None
                disk_ref = None
                
                for line in output_lines:
                    if "Formatting" in line and "fmt=raw" in line:
                        # Extract path from: "Formatting '/var/lib/vz/images/100/opencore-test.raw', fmt=raw size=157286400"
                        start = line.find("'") + 1
                        end = line.find("'", start)
                        if start > 0 and end > start:
                            disk_path = line[start:end]
                    elif "successfully created" in line:
                        # Extract reference from: "successfully created 'local:100/opencore-test.raw'"
                        start = line.find("'") + 1
                        end = line.find("'", start)
                        if start > 0 and end > start:
                            disk_ref = line[start:end]
                
                if disk_path:
                    log(f"Created new disk at: {disk_path}")
                elif "already exists" in result.stderr:
                    # Disk already exists, construct the path
                    disk_path = f"/var/lib/vz/images/{vmid}/{disk_name}"
                    disk_ref = f"local:{vmid}/{disk_name}"
                    log(f"Using existing disk at: {disk_path}")
                else:
                    error(f"Could not determine disk path from pvesm output: {result.stdout}")
                    return False
                    
                # Set disk_ref if not already set
                if not disk_ref:
                    disk_ref = f"local:{vmid}/{disk_name}"
                    
            else:
                error(f"Failed to allocate disk: {result.stderr}")
                return False
            
            # Copy our IMG to the allocated disk
            log(f"Copying IMG to managed disk: {disk_path}")
            if not ssh(f"cp {temp_img_path} {disk_path}"):
                error("Failed to copy IMG to managed disk")
                return False
                
            log("IMG successfully copied to managed disk")
            
            # Configure VM to use the disk
            log(f"Configuring VM {vmid} to use disk: {disk_ref}")
            if not ssh(f"qm set {vmid} --ide0 {disk_ref},format=raw,cache=writeback,media=disk"):
                error("Failed to configure VM")
                return False
                
            log("VM configured successfully")
            
        finally:
            # Clean up temporary file
            log("Cleaning up temporary IMG file...")
            ssh(f"rm -f {temp_img_path}")  # Don't fail if cleanup fails
        
        # Start the VM
        info(f"Starting VM {vmid}")
        if not ssh(f"qm start {vmid}"):
            error("Failed to start VM")
            return False
            
        log(f"VM {vmid} started successfully with IMG")
        return True
        
    except Exception as e:
        error(f"IMG deployment failed: {e}")
        # Try to cleanup temp file on error
        try:
            ssh(f"rm -f /tmp/{img_filename}")
        except:
            pass
        return False

def deploy_iso(changeset_name, vmid, config):
    """Deploy ISO file to Proxmox VM via SSH"""
    try:
        # Check that ISO file exists
        iso_filename = f'opencore-{changeset_name}.iso'
        iso_path = ROOT / 'out' / iso_filename
        
        if not iso_path.exists():
            # Also check for just opencore.iso
            generic_iso = ROOT / 'out' / 'opencore.iso'
            if generic_iso.exists():
                iso_filename = 'opencore.iso'
                iso_path = generic_iso
                log(f"Found generic ISO file: {generic_iso}")
            else:
                error(f"ISO file not found: {iso_path}")
                error("Please build the ISO first using build-iso.py")
                return False
        else:
            log(f"Found ISO file: {iso_path}")
        
        # Copy ISO to remote host
        remote_iso_path = f"{config['remote_iso_dir']}/{iso_filename}"
        info(f"Copying ISO to {config['host']}:{remote_iso_path}")
        
        if not scp(iso_path, remote_iso_path):
            error("Failed to copy ISO to remote host")
            return False
            
        log("ISO copied successfully")
        
        # Deploy to VM via SSH
        info(f"Deploying ISO to VM {vmid}")
        
        # Stop the VM
        info(f"Stopping VM {vmid}")
        if not ssh(f"qm stop {vmid}"):
            warn(f"Could not stop VM {vmid} (may already be stopped)")
        
        # Configure VM to boot from the ISO
        log(f"Configuring VM {vmid} to use ISO")
        if not ssh(f"qm set {vmid} --ide0 {remote_iso_path},media=cdrom"):
            error("Failed to configure VM")
            return False
            
        # Start the VM
        info(f"Starting VM {vmid}")
        if not ssh(f"qm start {vmid}"):
            error("Failed to start VM")
            return False
            
        log(f"VM {vmid} started successfully with ISO")
        return True
        
    except Exception as e:
        error(f"ISO deployment failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Full Deploy Workflow: Apply changeset → Build IMG/ISO → Deploy to Proxmox',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This workflow combines three operations in sequence:
1. Apply the specified changeset to OpenCore configuration
2. Build an OpenCore IMG (default) or ISO from the configuration  
3. Deploy the IMG/ISO to a Proxmox VM and start it

By default, creates a 50MB IMG file for faster deployment and smaller storage usage.
Use --iso to create an ISO file instead (traditional OpenCore deployment method).

With --iso-only, step 1 is skipped (no fetch, apply, or validation),
and the workflow goes directly to building the ISO and deploying.

With --build-only, the workflow builds the IMG/ISO but does not deploy.

Example:
  python3.11 full-deploy.py myconfig --force
  python3.11 full-deploy.py myconfig --build-only
  python3.11 full-deploy.py myconfig --iso
  python3.11 full-deploy.py myconfig --iso-only --force
        """
    )
    parser.add_argument('changeset', help='Changeset name (without .yaml extension)')
    parser.add_argument('--force', '-f', action='store_true', help='Force rebuild of IMG/ISO')
    parser.add_argument('--build-only', '-b', action='store_true', help='Build only, do not deploy')
    parser.add_argument('--iso-only', '-i', action='store_true', help='Skip fetch/apply/validation, build ISO and deploy only')
    parser.add_argument('--iso', action='store_true', help='Build ISO instead of IMG (default is IMG)')
    
    args = parser.parse_args()
    
    # Validate argument combinations
    if args.iso_only and args.force:
        error("Cannot use --iso-only and --force together. --iso-only skips the apply step, making --force redundant.")
        return 1
    
    if args.build_only and args.force:
        error("Cannot use --build-only and --force together. --build-only skips the apply step, making --force redundant.")
        return 1
    
    if args.iso_only and args.build_only:
        error("Cannot use --iso-only and --build-only together. Choose one build-only mode.")
        return 1
    
    # When using --iso-only, force ISO mode
    use_iso = args.iso or args.iso_only
    
    try:
        if full_deploy_workflow(args.changeset, args.force, args.build_only, args.iso_only, use_iso):
            return 0
        else:
            return 1
    except KeyboardInterrupt:
        warn("Workflow cancelled by user")
        return 1
    except Exception as e:
        error(f"Workflow failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
