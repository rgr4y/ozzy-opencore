#!/usr/bin/env python3.11
"""
Refactored deploy.py using common libraries.

This script handles deployment of OpenCore configurations to Proxmox VMs
with support for changesets and remote operations.
"""

import os
import sys
import subprocess
import argparse
import shlex
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from lib import (
    ROOT, log, warn, error, info,
    load_config, run_command, get_remote_config,
    scp, ssh, validate_file_exists,
    load_changeset, get_changeset_path
)

def build_opencore_iso(force_rebuild=False):
    """Build the OpenCore ISO using the build script"""
    log("Building OpenCore ISO...")
    
    # Check if we need to clean first
    if force_rebuild:
        out_dir = ROOT / 'out'
        if out_dir.exists():
            log("Cleaning previous build...")
            run_command(f'rm -rf "{out_dir}"/*', check=False)
    
    build_script = ROOT / 'bin' / 'build_isos.sh'
    validate_file_exists(build_script, "Build script")
    
    # Make sure the script is executable
    run_command(f'chmod +x "{build_script}"')
    
    # Run the build script
    return run_command(f'bash "{build_script}"', "Building OpenCore ISO")

def deploy_to_proxmox(changeset_name=None, force_rebuild=False):
    """Deploy OpenCore configuration to Proxmox VM"""
    
    # Load environment configuration
    load_config()
    config = get_remote_config()
    
    # If rebuilding, fetch assets first if they don't exist
    if force_rebuild:
        ocvalidate_path = ROOT / "out" / "opencore" / "Utilities" / "ocvalidate" / "ocvalidate"
        if not ocvalidate_path.exists():
            log("Fetching OpenCore assets for rebuild...")
            fetch_script = ROOT / "scripts" / "fetch-assets.py"
            if fetch_script.exists():
                run_command(f'python3 "{fetch_script}"', "Fetching OpenCore assets")
            else:
                error("fetch-assets.py not found")
                return False
    else:
        # Check that OpenCore assets are available for validation
        ocvalidate_path = ROOT / "out" / "opencore" / "Utilities" / "ocvalidate" / "ocvalidate"
        if not ocvalidate_path.exists():
            error("OpenCore tools not found")
            error(f"Expected ocvalidate at: {ocvalidate_path}")
            error("Please run './ozzy fetch' first to download OpenCore")
            return False
    
    vmid = config['vmid']
    workdir = config['workdir']
    installer_iso = config['installer_iso']
    
    log(f"Deploying to VM {vmid} on Proxmox")
    
    # Apply changeset if specified
    changeset_data = None
    if changeset_name:
        changeset_path = get_changeset_path(changeset_name)
        validate_file_exists(changeset_path, "Changeset file")
        
        # Load changeset data for Proxmox configuration
        changeset_data = load_changeset(changeset_name)
        if not changeset_data:
            return False
        
        log(f"Applying changeset: {changeset_name}")
        # Use the same Python interpreter that's running this script
        cmd = [sys.executable, str(ROOT / "scripts" / "apply_changeset.py"), str(changeset_path)]
        log(f"Running: {' '.join(cmd)}")
        
        try:
            subprocess.check_call(cmd, cwd=ROOT)
        except subprocess.CalledProcessError as e:
            error(f"Failed to apply changeset: {e}")
            return False
        
        # Validate the configuration (required for deployment)
        validate_script = ROOT / "scripts" / "validate.sh"
        if ocvalidate_path.exists():
            log("Validating OpenCore configuration...")
            if not run_command(f'bash "{validate_script}"', "Validating configuration"):
                return False
        else:
            error("ocvalidate not found - cannot validate configuration")
            return False
    
    # Build or check for existing ISO
    iso_path = ROOT / 'out' / 'opencore.iso'
    
    if force_rebuild or not iso_path.exists():
        if not build_opencore_iso(force_rebuild):
            return False
    
    validate_file_exists(iso_path, "OpenCore ISO")
    log(f"Using OpenCore ISO: {iso_path}")
    
    # Upload ISO to Proxmox
    log("Uploading OpenCore ISO to Proxmox...")
    if not scp(iso_path, f'{workdir}/'):
        return False
    
    # Copy ISO to Proxmox ISO storage
    iso_name = iso_path.name
    log("Installing ISO to Proxmox storage...")
    if not ssh(f"cp {workdir}/{iso_name} /var/lib/vz/template/iso/{iso_name}"):
        return False
    
    # Stop VM if running (must be done before configuration changes)
    log(f"Stopping VM {vmid}...")
    ssh(f"qm stop {vmid} || true")
    ssh(f"sleep 3")  # Give VM time to stop completely
    
    # Process Proxmox VM configuration from changeset
    if changeset_data and 'proxmox_vm' in changeset_data:
        proxmox_config = changeset_data['proxmox_vm']
        log("Processing Proxmox VM configuration from changeset...")
        
        # Upload assets (like GPU BIOS ROM files)
        if 'assets' in proxmox_config:
            for asset in proxmox_config['assets']:
                src_relative = asset['src']
                dest_path = asset['dest']
                mode = asset.get('mode', '0644')
                
                # Handle relative paths properly
                if src_relative.startswith('./'):
                    src_path = ROOT / src_relative[2:]  # Remove "./" prefix
                else:
                    src_path = ROOT / src_relative
                
                if src_path.exists():
                    log(f"Uploading asset: {src_path} -> {dest_path}")
                    # Upload to workdir first
                    if not scp(src_path, f'{workdir}/'):
                        return False
                    # Move to final destination and set permissions
                    if not ssh(f"mv {workdir}/{src_path.name} {dest_path}"):
                        return False
                    if not ssh(f"chmod {mode} {dest_path}"):
                        return False
                    log(f"Asset deployed: {dest_path} (mode: {mode})")
                else:
                    error(f"Asset not found: {src_path}")
                    return False
        
        # Apply VM configuration overrides (VM must be stopped first)
        if 'conf_overrides' in proxmox_config:
            vm_id = proxmox_config.get('vmid', vmid)
            log(f"Applying VM configuration overrides for VM {vm_id}...")
            
            for key, value in proxmox_config['conf_overrides'].items():
                log(f"Setting {key} = {value}")
                if not ssh(f"qm set {vm_id} -{key} '{value}'"):
                    return False
        else:
            # Check if VM config exists and upload it (legacy support)
            vm_config = ROOT / 'proxmox' / f'{vmid}.conf'
            if vm_config.exists():
                log(f"Uploading legacy VM configuration: {vm_config}")
                if not scp(vm_config, f'/etc/pve/qemu-server/{vmid}.conf'):
                    return False
    else:
        # No changeset, try legacy config
        vm_config = ROOT / 'proxmox' / f'{vmid}.conf'
        if vm_config.exists():
            log(f"Uploading legacy VM configuration: {vm_config}")
            if not scp(vm_config, f'/etc/pve/qemu-server/{vmid}.conf'):
                return False
    
    # Configure VM storage (unless overridden by changeset)
    configure_storage = True
    if changeset_data and 'proxmox_vm' in changeset_data:
        proxmox_config = changeset_data['proxmox_vm']
        if 'conf_overrides' in proxmox_config:
            # Check if IDE configuration is handled by changeset
            overrides = proxmox_config['conf_overrides']
            if any(key.startswith('ide') for key in overrides.keys()):
                log("IDE configuration handled by changeset, skipping default storage setup")
                configure_storage = False
    
    if configure_storage:
        log("Configuring VM storage...")
        if not ssh(f"qm set {vmid} -ide0 local:iso/{iso_name},media=disk,cache=unsafe,size=10M"):
            return False
        if not ssh(f"qm set {vmid} -ide2 local:iso/{installer_iso},cache=unsafe"):
            return False
    
    # Start VM
    log(f"Starting VM {vmid}...")
    if not ssh(f"qm start {vmid}"):
        return False
    
    log(f"Deployment complete! VM {vmid} should now be booting with OpenCore")
    info("You can access the VM console via Proxmox web interface")
    return True

def check_status():
    """Check the status of the deployment environment"""
    load_config()
    config = get_remote_config()
    
    log("Deployment Status")
    info(f"Proxmox Host: {config['host']}")
    info(f"VM ID: {config['vmid']}")
    info(f"User: {config['user']}")
    
    # Check local files
    iso_path = ROOT / 'out' / 'opencore.iso'
    config_path = ROOT / 'out' / 'efi' / 'EFI' / 'OC' / 'config.plist'
    
    log("Local Files:")
    status_iso = "✓" if iso_path.exists() else "✗"
    status_config = "✓" if config_path.exists() else "✗"
    info(f"OpenCore ISO: {status_iso} {iso_path}")
    info(f"Config.plist: {status_config} {config_path}")
    
    # Check changesets
    from lib import list_available_changesets
    changesets = list_available_changesets()
    if changesets:
        log("Available Changesets:")
        for cs in changesets:
            info(f"- {cs}")
    
    # Try to check VM status on Proxmox (if accessible)
    try:
        log("Proxmox VM Status:")
        result = subprocess.run(
            f"ssh -o ConnectTimeout=5 {config['user']}@{config['host']} 'qm status {config['vmid']}'", 
            shell=True, capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            info(f"VM {config['vmid']}: {result.stdout.strip()}")
        else:
            warn(f"Could not check VM status: {result.stderr.strip()}")
    except (subprocess.TimeoutExpired, Exception) as e:
        warn(f"Cannot connect to Proxmox: {e}")

def main():
    parser = argparse.ArgumentParser(description='Deploy OpenCore configuration to Proxmox VM')
    parser.add_argument('--changeset', '-c', help='Apply a specific changeset before deployment')
    parser.add_argument('--rebuild', '-r', action='store_true', help='Force rebuild of OpenCore ISO')
    parser.add_argument('--build-only', '-b', action='store_true', help='Only build the ISO, do not deploy')
    parser.add_argument('--status', '-s', action='store_true', help='Check deployment status')
    
    args = parser.parse_args()
    
    if args.status:
        check_status()
        return 0
    
    if args.build_only:
        log("Building OpenCore ISO only...")
        
        # Apply changeset if specified
        if args.changeset:
            changeset_path = get_changeset_path(args.changeset)
            if not changeset_path.exists():
                error(f'Changeset not found: {changeset_path}')
                return 1
            
            log(f"Applying changeset: {args.changeset}")
            cmd = [sys.executable, str(ROOT / "scripts" / "apply_changeset.py"), str(changeset_path)]
            try:
                subprocess.check_call(cmd, cwd=ROOT)
            except subprocess.CalledProcessError as e:
                error(f"Failed to apply changeset: {e}")
                return 1
            
            # Validate the configuration (only if ocvalidate exists)
            validate_script = ROOT / "scripts" / "validate.sh"
            ocvalidate_path = ROOT / "out" / "opencore" / "Utilities" / "ocvalidate" / "ocvalidate"
            if ocvalidate_path.exists():
                log("Validating OpenCore configuration...")
                if not run_command(f'bash "{validate_script}"', "Validating configuration"):
                    return 1
            else:
                warn("Skipping validation (ocvalidate not available)")
        
        if build_opencore_iso(args.rebuild):
            log("Build complete!")
            return 0
        else:
            return 1
    
    try:
        if deploy_to_proxmox(args.changeset, args.rebuild):
            return 0
        else:
            return 1
    except KeyboardInterrupt:
        warn("Deployment cancelled by user")
        return 1
    except Exception as e:
        error(f"Deployment failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
