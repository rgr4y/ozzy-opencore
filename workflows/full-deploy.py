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
from lib import ROOT, log, warn, error, info, run_command, load_config, get_remote_config, scp, ssh, list_newest_changesets, paths as pm, cleanup_macos_metadata
from lib.efi_builder import build_iso_artifact, build_img_artifact, build_efi_then_validate

def full_deploy_workflow(changeset_name, force=False, build_only=False, iso_only=False, use_iso=False, local_efi=False):
    """Execute the full deployment workflow: changeset → IMG/ISO → Proxmox"""
    
    build_type = "ISO" if use_iso else "IMG"
    log(f"Starting full deployment workflow for changeset: {changeset_name} (building {build_type})")
    if local_efi:
        info("Local EFI deployment enabled: will deploy to mounted EFI and skip Proxmox")
    
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
    
    # Step 2: Build artifacts or just EFI for local deployment
    if local_efi:
        log("Step 2/2: Building EFI (no artifact) for local deployment...")
        # If we already applied above, don't apply again inside builder
        applied_already = not (iso_only or build_only)
        if not build_efi_then_validate(changeset_name, force_rebuild=force, no_validate=False, apply_changeset=not applied_already):
            return False
        # Deploy locally and finish
        return deploy_to_local_efi(changeset_name)
    else:
        step_num = "1/2" if iso_only else "2/3"
        log(f"Step {step_num}: Building OpenCore {build_type}...")
        applied_already = not (iso_only or build_only)
        built = build_iso_artifact(changeset_name, force_rebuild=force, no_validate=False, apply_changeset=not applied_already) if use_iso \
            else build_img_artifact(changeset_name, force_rebuild=force, no_validate=False, apply_changeset=not applied_already)
        if not built:
            return False
        log(f"✓ {build_type} built successfully")
    
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
        img_path = pm.build_root / img_filename

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

        # Run all VM-side operations in a single SSH session for fewer round-trips
        disk_name = f"opencore-{changeset_name}.raw"
        remote_script = f"""
            set -e
            echo "Stopping VM {vmid} (ignore if already stopped)" || true
            qm stop {vmid} || true
            echo "Allocating managed disk: {disk_name}"
            if ! pvesm alloc local {vmid} {disk_name} 150M --format raw; then
              echo "Disk may already exist, proceeding"
            fi
            echo "Resolving disk path"
            DISK_REF="local:{vmid}/{disk_name}"
            DISK_PATH=$(pvesm path "$DISK_REF")
            echo "Copying image to $DISK_PATH"
            cp {temp_img_path} "$DISK_PATH"
            echo "Configuring VM to use disk"
            qm set {vmid} --ide0 "$DISK_REF",format=raw,cache=writeback,media=disk
            echo "Cleaning up temp image"
            rm -f {temp_img_path} || true
            echo "Starting VM {vmid}"
            qm start {vmid}
        """.strip()
        if not ssh(f"bash -lc {sh_quote(remote_script)}"):
            error("Remote deployment script failed")
            return False

        log(f"VM {vmid} started successfully with IMG")
        return True

    except Exception as e:
        error(f"IMG deployment failed: {e}")
        # Try to cleanup temp file on error
        try:
            ssh(f"rm -f /tmp/{img_filename}")
        except Exception:
            pass
        return False

def deploy_iso(changeset_name, vmid, config):
    """Deploy ISO file to Proxmox VM via SSH"""
    try:
        # Check that ISO file exists (support generic default)
        iso_filename = f'opencore-{changeset_name}.iso'
        iso_path = pm.opencore_iso if pm.opencore_iso.exists() else (pm.build_root / iso_filename)

        if not iso_path.exists():
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

        # Configure and start VM in a single SSH session
        remote_script = f"""
            set -e
            echo "Stopping VM {vmid} (ignore if already stopped)" || true
            qm stop {vmid} || true
            echo "Configuring VM to use ISO"
            qm set {vmid} --ide0 {remote_iso_path},media=cdrom
            echo "Starting VM {vmid}"
            qm start {vmid}
        """.strip()
        if not ssh(f"bash -lc {sh_quote(remote_script)}"):
            error("Remote ISO deployment script failed")
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
    parser.add_argument('--local-efi', action='store_true', help='Deploy locally to mounted EFI (inside VM/Hackintosh)')
    
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
        if full_deploy_workflow(args.changeset, args.force, args.build_only, args.iso_only, use_iso, args.local_efi):
            return 0
        else:
            return 1
    except KeyboardInterrupt:
        warn("Workflow cancelled by user")
        return 1
    except Exception as e:
        error(f"Workflow failed: {e}")
        return 1

def sh_quote(s: str) -> str:
    """Minimal single-arg shell quoting for remote inline scripts."""
    return "'" + s.replace("'", "'\\''") + "'"

def deploy_to_local_efi(changeset_name: str) -> bool:
    """Attempt to deploy built EFI to the locally mounted EFI partition.

    Strategy (macOS):
    - Prefer /Volumes/OZZY-OC if present (label used by our images)
    - Else try to mount any EFI partitions and detect one with OC/OpenCore.efi
    """
    import subprocess, shutil
    target = Path('/Volumes/OZZY-OC')
    source_efi = pm.efi_build / 'EFI'
    if not source_efi.exists():
        error(f"Source EFI not found: {source_efi}")
        return False
    if target.exists():
        log(f"Deploying to local EFI at {target}")
        try:
            # Remove any macOS metadata from source to avoid AppleDouble issues
            try:
                cleanup_macos_metadata(source_efi)
            except Exception:
                pass
            # Remove existing EFI folder and copy new, ignoring Apple metadata files
            if (target / 'EFI').exists():
                # Some volumes can contain broken AppleDouble entries; ignore deletion errors
                shutil.rmtree(target / 'EFI', ignore_errors=True)
            ignore = shutil.ignore_patterns('._*', '__MACOSX', '.DS_Store')
            shutil.copytree(source_efi, target / 'EFI', ignore=ignore)
            # Clean up any metadata that slipped through
            try:
                cleanup_macos_metadata(target / 'EFI')
            except Exception:
                pass
            # Manage changeset marker at volume root
            for old in target.glob('*.changeset'):
                try:
                    old.unlink()
                except Exception:
                    pass
            marker = target / f"{changeset_name}.changeset"
            try:
                marker.touch()
            except Exception:
                pass
            log("✓ Deployed EFI to local volume")
            return True
        except Exception as e:
            error(f"Failed to deploy to local EFI: {e}")
            return False
    # Fallback: try to mount common EFI mountpoint
    # Attempt to mount diskXs1 where X from diskutil list
    try:
        result = subprocess.run(['diskutil', 'list'], capture_output=True, text=True)
        candidates = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.endswith('EFI') and 'EFI' in line and 'disk' in line:
                # crude parse: look for diskXs1 pattern in the line
                parts = line.split()
                for p in parts:
                    if p.startswith('disk') and 's' in p:
                        candidates.append(p)
        for dev in candidates:
            subprocess.run(['diskutil', 'mount', dev], capture_output=True)
        # Retry preferred mount
        if target.exists():
            return deploy_to_local_efi(changeset_name)
    except Exception:
        pass
    error("Could not find a mounted EFI volume to deploy to. Use --usb-path via build-usb.py or mount EFI manually.")
    return False

if __name__ == '__main__':
    sys.exit(main())
