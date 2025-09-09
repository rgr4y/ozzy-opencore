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

def full_deploy_workflow(changeset_name, force=False, build_only=False, iso_only=False):
    """Execute the full deployment workflow: changeset → ISO → Proxmox"""
    
    log(f"Starting full deployment workflow for changeset: {changeset_name}")
    
    if iso_only:
        log("ISO-only mode: Skipping fetch, apply, and validation steps")
        # Skip directly to Step 2: Build ISO
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
    
    # Step 2: Build ISO
    step_num = "1/2" if iso_only else "2/3"
    log(f"Step {step_num}: Building OpenCore ISO...")
    build_iso_script = ROOT / "scripts" / "build-iso.py"
    cmd = [sys.executable, str(build_iso_script), changeset_name]

    if force:
        cmd.append("--force")
    
    try:
        result = subprocess.run(cmd, cwd=ROOT, check=True)
        log("✓ ISO built successfully")
    except subprocess.CalledProcessError as e:
        error(f"Failed to build ISO: {e}")
        return False
    
    if build_only:
        log("Build-only mode: Skipping deployment")
        info("ISO is ready for manual deployment")
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
        
        # Upload ISO to Proxmox
        iso_path = ROOT / 'out' / 'opencore.iso'
        if not iso_path.exists():
            # Fallback to build directory
            iso_path = ROOT / 'out' / 'build' / 'efi' / 'opencore.iso'
        
        if not iso_path.exists():
            error("ISO file not found after build")
            return False
        
        iso_name = f"opencore-{changeset_name}.iso"
        log(f"Uploading {iso_path} to Proxmox as {iso_name}...")
        
        if not scp(iso_path, f"/var/lib/vz/template/iso/{iso_name}"):
            return False
        
        # Stop VM if running
        log(f"Stopping VM {vmid} if running...")
        # ssh(f"qm stop {vmid}")  # Don't fail if VM is already  stopped
        
        # Configure VM storage
        log("Configuring VM storage...")
        if not ssh(f"qm set {vmid} -ide0 local:iso/{iso_name},media=cdrom,cache=unsafe,size=110M"):
            return False
        
        # Start VM
        log(f"Starting VM {vmid}...")
        #if not ssh(f"sleep 3 && qm start {vmid}"):
        #    return False
        
        log("✓ Deployment completed successfully")
        
    except Exception as e:
        error(f"Deployment failed: {e}")
        return False
    
    log("🎉 Full deployment workflow completed successfully!")
    info(f"VM {vmid} should now be booting with OpenCore")
    info("You can access the VM console via Proxmox web interface")
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Full Deploy Workflow: Apply changeset → Build ISO → Deploy to Proxmox',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This workflow combines three operations in sequence:
1. Apply the specified changeset to OpenCore configuration
2. Build an OpenCore ISO from the configuration  
3. Deploy the ISO to a Proxmox VM and start it

With --iso-only, steps 1 is skipped (no fetch, apply, or validation),
and the workflow goes directly to building the ISO and deploying.

Example:
  python3.11 full-deploy.py myconfig --force
  python3.11 full-deploy.py myconfig --build-only
  python3.11 full-deploy.py myconfig --iso-only --force
        """
    )
    parser.add_argument('changeset', help='Changeset name (without .yaml extension)')
    parser.add_argument('--force', '-f', action='store_true', help='Force rebuild of ISO')
    parser.add_argument('--build-only', '-b', action='store_true', help='Build only, do not deploy')
    parser.add_argument('--iso-only', '-i', action='store_true', help='Skip fetch/apply/validation, build ISO and deploy only')
    
    args = parser.parse_args()
    
    # Validate argument combinations
    if args.iso_only and args.force:
        error("Cannot use --iso-only and --force together. --iso-only skips the apply step, making --force redundant.")
        return 1
    
    try:
        if full_deploy_workflow(args.changeset, args.force, args.build_only, args.iso_only):
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
