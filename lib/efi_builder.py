#!/usr/bin/env python3.11
"""
EFI Builder Library

Common functions for building complete OpenCore EFI structu    if 'UefiDrivers' in changeset_data:
        log("Processing UEFI drivers...")
        
        # Get drivers from changeset
        for driver in changeset_data['UefiDrivers']:nsures all components (ACPI, Drivers, Tools, Kexts, etc.) are properly included.
"""

import shutil
import subprocess
import yaml
import zipfile
import tempfile
from pathlib import Path
from . import ROOT, log, warn, error, info, run_command, get_project_paths, ensure_directory, cleanup_macos_metadata

def manage_changeset_kexts(changeset_name, target_efi_dir):
    """
    Prune kexts in the EFI structure to only include those specified in the changeset.
    
    Args:
        changeset_name: Name of the changeset
        target_efi_dir: Target EFI directory (typically out/build/efi/EFI)
        
    Returns:
        bool: True if successful, False otherwise
    """
    paths = get_project_paths()
    changeset_path = paths['changesets'] / f"{changeset_name}.yaml"
    
    if not changeset_path.exists():
        error(f"Changeset file not found: {changeset_path}")
        return False
    
    # Load changeset to get kext specifications
    try:
        with open(changeset_path, 'r') as f:
            changeset_data = yaml.safe_load(f)
    except Exception as e:
        error(f"Failed to load changeset: {e}")
        return False
    
    if 'Kexts' not in changeset_data:
        log("No kexts specified in changeset")
        return True
    
    # Get the kexts directory
    kexts_dir = target_efi_dir / 'OC' / 'Kexts'
    if not kexts_dir.exists():
        error(f"Kexts directory not found: {kexts_dir}")
        return False
    
    # Get list of kexts specified in changeset
    changeset_kexts = set()
    for kext_info in changeset_data['Kexts']:
        changeset_kexts.add(kext_info['bundle'])
    
    log(f"Changeset specifies {len(changeset_kexts)} kexts")
    
    # Remove kexts not in changeset
    removed_count = 0
    for kext_item in kexts_dir.iterdir():
        if kext_item.is_dir() and kext_item.name.endswith('.kext'):
            if kext_item.name not in changeset_kexts:
                log(f"Removing unused kext: {kext_item.name}")
                shutil.rmtree(kext_item)
                removed_count += 1
            else:
                log(f"✓ Keeping changeset kext: {kext_item.name}")
    
    # Verify all changeset kexts are present
    missing_kexts = []
    for kext_name in changeset_kexts:
        kext_path = kexts_dir / kext_name
        if not kext_path.exists():
            missing_kexts.append(kext_name)
    
    if missing_kexts:
        error(f"Missing required kexts: {', '.join(missing_kexts)}")
        return False
    
    log(f"✓ Kext management complete: removed {removed_count}, kept {len(changeset_kexts)}")
    return True

def manage_changeset_drivers(changeset_name, target_efi_dir):
    """
    Copy drivers specified in changeset to the EFI Drivers directory.
    
    Args:
        changeset_name: Name of the changeset
        target_efi_dir: Target EFI directory containing OC subfolder
        
    Returns:
        bool: True if successful, False otherwise
    """
    from . import log, warn, error
    from .changeset import load_changeset
    import shutil
    
    # Load changeset
    changeset_data = load_changeset(changeset_name)
    if not changeset_data:
        error(f"Failed to load changeset: {changeset_name}")
        return False
    
    # Get the drivers directory
    drivers_dir = target_efi_dir / 'OC' / 'Drivers'
    drivers_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy drivers specified in changeset
    if 'UefiDrivers' in changeset_data:
        log(f"Copying drivers specified in changeset...")
        copied_count = 0
        
        for driver in changeset_data['UefiDrivers']:
            driver_name = driver['path']
            
            # Skip if already exists (e.g. essential drivers)
            target_driver = drivers_dir / driver_name
            if target_driver.exists():
                log(f"Driver already exists: {driver_name}")
                continue
            
            # Look for drivers in various locations
            source_locations = [
                ROOT / "out" / "opencore" / "X64" / "EFI" / "OC" / "Drivers" / driver_name,
                ROOT / "out" / "ocbinarydata-repo" / "Drivers" / driver_name,
                ROOT / "out" / "opencore" / "Drivers" / driver_name,
                ROOT / "assets" / "drivers" / driver_name,
            ]
            
            source_driver = None
            for location in source_locations:
                if location.exists():
                    source_driver = location
                    break
            
            if source_driver:
                shutil.copy2(source_driver, target_driver)
                log(f"Copied driver: {driver_name}")
                copied_count += 1
            else:
                warn(f"Driver not found: {driver_name} (searched in {len(source_locations)} locations)")
        
        log(f"Driver management completed: {copied_count} drivers copied")
    
    return True

def build_complete_efi_structure(changeset_name, force_rebuild=False):
    """
    Build a complete EFI structure with OpenCore, kexts, drivers, and applied changeset.
    This is the unified function used by both USB and ISO builders.
    
    Args:
        changeset_name: Name of the changeset to apply
        force_rebuild: Whether to force a complete rebuild
        
    Returns:
        bool: True if successful, False otherwise
    """
    from .common import get_project_paths, log, error, run_command
    import subprocess
    import sys
    
    paths = get_project_paths()
    target_dir = paths['out'] / 'build' / 'efi' / 'EFI'
    
    log(f"Building complete EFI structure in: {target_dir.parent}")
    
    # Check if fetch is needed (no kexts or force rebuild)
    kexts_dir = target_dir / 'OC' / 'Kexts'
    if force_rebuild or not kexts_dir.exists() or not any(kexts_dir.glob('*.kext')):
        log("Fetched assets missing or force rebuild requested, running fetch...")
        fetch_script = paths['scripts'] / 'fetch-assets.py'
        if not run_command(f'python3.11 "{fetch_script}"', "Fetching assets"):
            error("Failed to fetch assets")
            return False
    
    # Apply changeset to create config.plist
    log(f"Applying changeset: {changeset_name}")
    apply_script = paths['scripts'] / 'apply-changeset.py'
    if not run_command(f'python3.11 "{apply_script}" "{changeset_name}"', "Applying changeset"):
        error("Failed to apply changeset")
        return False
    
    # Prune kexts based on changeset
    if not manage_changeset_kexts(changeset_name, target_dir):
        error("Failed to manage kexts for changeset")
        return False
    
    # Copy drivers specified in changeset
    if not manage_changeset_drivers(changeset_name, target_dir):
        error("Failed to manage drivers for changeset")
        return False
    
    # Final validation
    log("Validating final EFI structure...")
    config_file = target_dir / 'OC' / 'config.plist'
    if not config_file.exists():
        error(f"Config file not found: {config_file}")
        return False
    
    # Validate with ocvalidate if available
    ocvalidate_path = paths['opencore'] / "Utilities" / "ocvalidate" / "ocvalidate"
    if ocvalidate_path.exists():
        if not run_command(f'"{ocvalidate_path}" "{config_file}"', "Validating with ocvalidate"):
            error("Configuration validation failed")
            return False
        log("✓ Configuration passed ocvalidate")
    
    log("✓ Complete EFI structure built successfully")
    return True

def copy_efi_for_build(source_efi_dir, target_build_dir, force_clean=True):
    """
    Copy EFI structure for build processes (ISO/USB).
    
    Args:
        source_efi_dir: Source EFI directory (typically out/efi/EFI)
        target_build_dir: Target build directory (typically out/build/efi)
        force_clean: Whether to clean target before copying
        
    Returns:
        bool: True if successful, False otherwise
    """
    source_efi = Path(source_efi_dir)
    target_build = Path(target_build_dir)
    
    if not source_efi.exists():
        error(f"Source EFI directory not found: {source_efi}")
        return False
    
    # Clean target if requested
    if force_clean and (target_build / 'EFI').exists():
        log("Cleaning existing build EFI structure...")
        shutil.rmtree(target_build / 'EFI')
    
    # Copy EFI structure to build directory
    log(f"Copying EFI structure to build directory...")
    try:
        ensure_directory(target_build)
        shutil.copytree(source_efi, target_build / 'EFI', dirs_exist_ok=False)
        log("✓ EFI structure copied to build directory")
        return True
    except Exception as e:
        error(f"Failed to copy EFI structure: {e}")
        return False
