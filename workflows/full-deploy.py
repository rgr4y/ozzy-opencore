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
from lib import ROOT, log, warn, error, info, run_command, load_config, get_remote_config, scp, ssh

def full_deploy_workflow(changeset_name, force_rebuild=False, build_only=False):
    """Execute the full deployment workflow: changeset → ISO → Proxmox"""
    
    log(f"Starting full deployment workflow for changeset: {changeset_name}")
    
    # Step 1: Apply changeset
    log("Step 1/3: Applying changeset...")
    apply_script = ROOT / "scripts" / "apply-changeset.py"
    changeset_path = ROOT / "config" / "changesets" / f"{changeset_name}.yaml"
    
    if not changeset_path.exists():
        error(f"Changeset not found: {changeset_path}")
        return False
    
    cmd = [sys.executable, str(apply_script), str(changeset_path)]
    try:
        result = subprocess.run(cmd, cwd=ROOT, check=True)
        log("✓ Changeset applied successfully")
    except subprocess.CalledProcessError as e:
        error(f"Failed to apply changeset: {e}")
        return False
    
    # Step 2: Build ISO
    log("Step 2/3: Building OpenCore ISO...")
    build_iso_script = ROOT / "scripts" / "build-iso.py"
    cmd = [sys.executable, str(build_iso_script)]
    if force_rebuild:
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
    log("Step 3/3: Deploying to Proxmox...")
    
    try:
        # Load environment configuration
        load_config()
        config = get_remote_config()
        
        vmid = config['vmid']
        workdir = config['workdir']
        installer_iso = config['installer_iso']
        
        log(f"Deploying to VM {vmid} on Proxmox")
        
        # Upload ISO to Proxmox
        iso_path = ROOT / 'out' / 'iso' / 'opencore.iso'
        if not iso_path.exists():
            # Fallback to build directory
            iso_path = ROOT / 'out' / 'build' / 'efi' / 'opencore.iso'
        
        if not iso_path.exists():
            error("ISO file not found after build")
            return False
        
        iso_name = f"opencore-{changeset_name}.iso"
        log(f"Uploading {iso_path} to Proxmox as {iso_name}...")
        
        if not scp(f"{iso_path}", f"/var/lib/vz/template/iso/{iso_name}"):
            return False
        
        # Stop VM if running
        log(f"Stopping VM {vmid} if running...")
        ssh(f"qm stop {vmid}", check=False)  # Don't fail if VM is already stopped
        
        # Configure VM storage
        log("Configuring VM storage...")
        if not ssh(f"qm set {vmid} -ide0 local:iso/{iso_name},media=disk,cache=unsafe,size=10M"):
            return False
        if not ssh(f"qm set {vmid} -ide2 local:iso/{installer_iso},cache=unsafe"):
            return False
        
        # Start VM
        log(f"Starting VM {vmid}...")
        if not ssh(f"qm start {vmid}"):
            return False
        
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

Example:
  python3.11 full-deploy.py myconfig --rebuild
  python3.11 full-deploy.py myconfig --build-only
        """
    )
    parser.add_argument('changeset', help='Changeset name (without .yaml extension)')
    parser.add_argument('--rebuild', '-r', action='store_true', help='Force rebuild of ISO')
    parser.add_argument('--build-only', '-b', action='store_true', help='Build only, do not deploy')
    
    args = parser.parse_args()
    
    try:
        if full_deploy_workflow(args.changeset, args.rebuild, args.build_only):
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
