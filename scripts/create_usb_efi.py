#!/usr/bin/env python3
"""
Refactored create_usb_efi.py using common libraries.

This script creates USB-ready OpenCore EFI structures for bare metal installation.
"""

import os
import sys
import subprocess
import argparse
import shutil
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from lib import (
    ROOT, log, warn, error, info,
    load_config, run_command, 
    ensure_directory, cleanup_macos_metadata,
    validate_file_exists, get_project_paths,
    load_changeset, save_changeset,
    validate_and_generate_smbios, list_changeset_kexts,
    get_changeset_path
)

def validate_required_kexts(changeset_name, output_dir):
    """Validate that all kexts specified in changeset are present"""
    paths = get_project_paths()
    kexts_dir = paths['efi_oc'] / 'Kexts'
    
    if not kexts_dir.exists():
        error(f"Kexts directory not found: {kexts_dir}")
        return False
    
    changeset_kexts = list_changeset_kexts(changeset_name)
    missing_kexts = []
    
    for kext_info in changeset_kexts:
        kext_name = kext_info['bundle']
        kext_path = kexts_dir / kext_name
        
        if not kext_path.exists():
            missing_kexts.append(kext_name)
        else:
            log(f"Found kext: {kext_name}")
    
    if missing_kexts:
        error("Missing required kexts:")
        for kext in missing_kexts:
            error(f"  - {kext}")
        error("Please run './ozzy fetch' first to download required kexts")
        return False
    
    log("All required kexts are available")
    return True

def create_usb_efi(changeset_name=None, output_dir=None, force_rebuild=False, dry_run=False, usb_path=None, skip_smbios_generation=False):
    """Create USB-ready EFI structure"""
    
    paths = get_project_paths()
    
    # Set default output directory
    if output_dir is None:
        output_dir = paths['usb_efi']
    else:
        output_dir = Path(output_dir)
    
    log(f"Creating USB EFI structure in: {output_dir}")
    
    if dry_run:
        log("DRY RUN MODE - No files will be created")
    
    # Apply changeset if specified
    if changeset_name:
        changeset_path = get_changeset_path(changeset_name)
        validate_file_exists(changeset_path, "Changeset file")
        
        # Validate kexts are available
        if not validate_required_kexts(changeset_name, output_dir):
            return False
        
        log(f"Applying changeset: {changeset_name}")
        if not dry_run:
            # Apply changeset using existing script
            cmd = [sys.executable, str(paths['scripts'] / "apply_changeset.py"), str(changeset_path)]
            try:
                subprocess.check_call(cmd, cwd=ROOT)
            except subprocess.CalledProcessError as e:
                error(f"Failed to apply changeset: {e}")
                return False
        
        # Generate SMBIOS if not skipped
        if not skip_smbios_generation:
            log("Generating SMBIOS data for USB deployment...")
            if not dry_run:
                changeset_data = load_changeset(changeset_name)
                if changeset_data:
                    if validate_and_generate_smbios(changeset_data, force=True):
                        if not save_changeset(changeset_name, changeset_data):
                            warn("Failed to save SMBIOS updates to changeset")
                    else:
                        warn("Failed to generate SMBIOS data")
    
    # Validate source EFI structure
    source_efi = paths['efi_build'] / 'EFI'
    validate_file_exists(source_efi, "Source EFI structure")
    validate_file_exists(source_efi / 'OC' / 'config.plist', "OpenCore configuration")
    
    if dry_run:
        log("Would copy EFI structure from source to output")
        log(f"Source: {source_efi}")
        log(f"Output: {output_dir}")
        return True
    
    # Create output directory and copy EFI structure
    ensure_directory(output_dir)
    
    # Clean existing EFI if rebuilding
    if force_rebuild and (output_dir / 'EFI').exists():
        log("Cleaning existing EFI structure...")
        shutil.rmtree(output_dir / 'EFI')
    
    # Copy EFI structure
    log("Copying EFI structure...")
    try:
        shutil.copytree(source_efi, output_dir / 'EFI', dirs_exist_ok=True)
    except Exception as e:
        error(f"Failed to copy EFI structure: {e}")
        return False
    
    # Clean up macOS metadata
    cleanup_count = cleanup_macos_metadata(output_dir)
    if cleanup_count > 0:
        log(f"Cleaned {cleanup_count} macOS metadata files")
    
    # Create deployment info file
    info_file = output_dir / 'DEPLOYMENT_INFO.txt'
    try:
        with open(info_file, 'w') as f:
            f.write(f"OpenCore USB EFI Deployment\n")
            f.write(f"Created: {subprocess.check_output(['date'], text=True).strip()}\n")
            if changeset_name:
                f.write(f"Changeset: {changeset_name}\n")
            f.write(f"\nInstructions:\n")
            f.write(f"1. Format USB drive as FAT32 with GUID partition table\n")
            f.write(f"2. Copy the entire EFI folder to the USB drive root\n")
            f.write(f"3. Boot from USB and proceed with macOS installation\n")
        log(f"Created deployment info: {info_file}")
    except Exception as e:
        warn(f"Failed to create deployment info: {e}")
    
    # Copy to USB path if specified
    if usb_path:
        usb_path = Path(usb_path)
        if not usb_path.exists():
            error(f"USB path not found: {usb_path}")
            return False
        
        log(f"Copying EFI to USB drive: {usb_path}")
        try:
            usb_efi_path = usb_path / 'EFI'
            if usb_efi_path.exists():
                log("Removing existing EFI on USB drive...")
                shutil.rmtree(usb_efi_path)
            
            shutil.copytree(output_dir / 'EFI', usb_efi_path)
            log("Successfully copied EFI to USB drive")
        except Exception as e:
            error(f"Failed to copy to USB drive: {e}")
            return False
    
    log(f"USB EFI structure created successfully in: {output_dir}")
    return True

def main():
    parser = argparse.ArgumentParser(description='Create USB-ready OpenCore EFI structure')
    parser.add_argument('--changeset', '-c', help='Apply named changeset configuration')
    parser.add_argument('--output', '-o', help='Output directory for USB EFI structure')
    parser.add_argument('--force', '-f', action='store_true', help='Force rebuild, overwrite existing files')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--usb-path', help='Path to USB drive to copy EFI structure to')
    parser.add_argument('--skip-smbios', action='store_true', help='Skip automatic SMBIOS generation')
    
    args = parser.parse_args()
    
    # Load environment configuration
    load_config()
    
    try:
        if create_usb_efi(
            changeset_name=args.changeset,
            output_dir=args.output,
            force_rebuild=args.force,
            dry_run=args.dry_run,
            usb_path=args.usb_path,
            skip_smbios_generation=args.skip_smbios
        ):
            log("USB EFI creation completed successfully")
            return 0
        else:
            error("USB EFI creation failed")
            return 1
    except KeyboardInterrupt:
        warn("Operation cancelled by user")
        return 1
    except Exception as e:
        error(f"Unexpected error: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
