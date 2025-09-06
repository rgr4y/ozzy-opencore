#!/usr/bin/env python3.11
"""
Deployment operations library.

This module handles all Proxmox deployment operations including building ISOs,
deploying configurations, and checking deployment status.
"""

import os
import sys
import subprocess
from pathlib import Path

# Import our common libraries
from .common import (
    ROOT, log, warn, error, info,
    load_config, run_command, get_remote_config,
    scp, ssh, validate_file_exists
)
from .changeset import load_changeset, get_changeset_path
from .paths import paths


def build_opencore_iso(force_rebuild=False):
    """Build the OpenCore ISO using the build script"""
    log("Building OpenCore ISO...")
    
    # Check if we need to clean first
    if force_rebuild:
        if paths.build_root.exists():
            log("Cleaning previous build...")
            run_command(f'rm -rf "{paths.build_root}"/*', check=False)
    
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
        ocvalidate_path = paths.opencore_root / "Utilities" / "ocvalidate" / "ocvalidate"
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
        ocvalidate_path = paths.opencore_root / "Utilities" / "ocvalidate" / "ocvalidate"
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
            warn("Skipping validation (ocvalidate not available)")
    
    # Build the OpenCore ISO
    if not build_opencore_iso(force_rebuild):
        return False
    
    # Upload ISO to Proxmox
    iso_path = paths.build_root / 'opencore.iso'
    validate_file_exists(iso_path, "OpenCore ISO")
    
    iso_name = f"opencore-{changeset_name}.iso" if changeset_name else "opencore.iso"
    log(f"Uploading {iso_path} to Proxmox as {iso_name}...")
    
    if not scp(f"{iso_path}", f"/var/lib/vz/template/iso/{iso_name}"):
        return False
    
    # Stop VM if running
    log(f"Stopping VM {vmid} if running...")
    ssh(f"qm stop {vmid}", check=False)  # Don't fail if VM is already stopped
    
    # Configure VM based on changeset
    configure_storage = True
    if changeset_data and 'proxmox' in changeset_data:
        proxmox_config = changeset_data['proxmox']
        log("Applying Proxmox configuration from changeset...")
        
        # Apply any custom Proxmox settings
        if 'overrides' in proxmox_config:
            overrides = proxmox_config['overrides']
            for key, value in overrides.items():
                log(f"Setting VM parameter: {key} = {value}")
                if not ssh(f"qm set {vmid} -{key} {value}"):
                    return False
            
            # Check if storage is being configured by changeset
            if any(key.startswith('ide') for key in overrides.keys()):
                log("IDE configuration handled by changeset, skipping default storage setup")
                configure_storage = False
    
    if configure_storage:
        log("Configuring VM storage...")
        if not ssh(f"qm set {vmid} -ide0 local:iso/{iso_name},media=disk,cache=unsafe,size=10M"):
            return False
    
    # Start VM
    log(f"Starting VM {vmid}...")
    if not ssh(f"qm start {vmid}"):
        return False
    
    log(f"Deployment complete! VM {vmid} should now be booting with OpenCore")
    info("You can access the VM console via Proxmox web interface")
    return True


def check_deployment_status():
    """Check the status of the deployment environment"""
    load_config()
    config = get_remote_config()
    
    log("Deployment Status")
    info(f"Proxmox Host: {config['host']}")
    info(f"VM ID: {config['vmid']}")
    info(f"User: {config['user']}")
    
    # Check local files
    iso_path = paths.build_root / 'opencore.iso'
    config_path = paths.oc_efi / 'config.plist'
    
    log("Local Files:")
    status_iso = "✓" if iso_path.exists() else "✗"
    status_config = "✓" if config_path.exists() else "✗"
    info(f"OpenCore ISO: {status_iso} {iso_path}")
    info(f"Config.plist: {status_config} {config_path}")
    
    # Check changesets
    from .common import list_available_changesets
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


def build_iso_only(changeset_name=None, force_rebuild=False):
    """Build OpenCore ISO without deploying"""
    log("Building OpenCore ISO only...")
    
    # Apply changeset if specified
    if changeset_name:
        changeset_path = get_changeset_path(changeset_name)
        if not changeset_path.exists():
            error(f'Changeset not found: {changeset_path}')
            return False
        
        log(f"Applying changeset: {changeset_name}")
        cmd = [sys.executable, str(ROOT / "scripts" / "apply_changeset.py"), str(changeset_path)]
        try:
            subprocess.check_call(cmd, cwd=ROOT)
        except subprocess.CalledProcessError as e:
            error(f"Failed to apply changeset: {e}")
            return False
        
        # Validate the configuration (only if ocvalidate exists)
        validate_script = ROOT / "scripts" / "validate.sh"
        ocvalidate_path = paths.opencore_root / "Utilities" / "ocvalidate" / "ocvalidate"
        if ocvalidate_path.exists():
            log("Validating OpenCore configuration...")
            if not run_command(f'bash "{validate_script}"', "Validating configuration"):
                return False
        else:
            warn("Skipping validation (ocvalidate not available)")
    
    if build_opencore_iso(force_rebuild):
        log("Build complete!")
        return True
    else:
        return False
