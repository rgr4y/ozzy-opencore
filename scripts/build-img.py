#!/usr/bin/env python3.11
"""
Build OpenCore IMG

This script builds an OpenCore .img file from the current EFI configuration.
The .img file is deployable directly to Proxmox VMs as a disk image.
"""

import sys
import argparse
import subprocess
from pathlib import Path

# Import our common libraries and improved workflow
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import (
    ROOT, log, warn, error, info,
    run_command, validate_file_exists,
    get_project_paths, ensure_directory, cleanup_macos_metadata,
    build_complete_efi_structure, copy_efi_for_build, validate_changeset_exists
)


def build_opencore_img(changeset_name, force_rebuild=False, no_validate=False):
    """
    Build the OpenCore .img file using the improved workflow.
    The resulting .img will be a 50MB raw disk image with EFI partition.
    """
    log("Building OpenCore IMG...")

    # Validate changeset exists
    try:
        validate_changeset_exists(changeset_name)
    except FileNotFoundError:
        return False

    # Get project paths
    paths = get_project_paths()

    # Clean previous build if requested
    if force_rebuild and paths['build_root'].exists():
        log("Cleaning previous build...")
        run_command(f'rm -rf "{paths["build_root"]}"/*', check=False)

    # Validate OpenCore assets
    ocvalidate_path = paths['opencore'] / "Utilities" / "ocvalidate" / "ocvalidate"
    if not ocvalidate_path.exists():
        error("OpenCore tools not found")
        error(f"Expected ocvalidate at: {ocvalidate_path}")
        error("Please run './ozzy fetch' first to download OpenCore assets")
        return False

    # Build complete EFI structure
    if not build_complete_efi_structure(changeset_name=changeset_name, force_rebuild=force_rebuild):
        error("Failed to build complete EFI structure")
        return False

    # Validate EFI structure
    source_efi = paths['out'] / 'build' / 'efi' / 'EFI'
    if not source_efi.exists():
        error(f"Source EFI structure not found: {source_efi}")
        return False

    # Optionally validate configuration
    if not no_validate:
        validate_script = paths['scripts'] / 'validate-config.py'
        if validate_script.exists():
            log("Validating OpenCore configuration before building...")
            if not run_command(f'python3.11 "{validate_script}"', "Validating configuration"):
                error("Configuration validation failed - not building IMG")
                return False
        else:
            warn("No validation script found, building without validation")

    # Build the .img file
    if not build_img_file(changeset_name, source_efi, paths):
        error("IMG build failed")
        return False

    # Check that IMG was created
    img_path = paths['out'] / f'opencore-{changeset_name}.img'
    if img_path.exists():
        log(f"OpenCore IMG created successfully: {img_path}")
        info("The IMG is ready for deployment to Proxmox.")
        return True
    else:
        error("IMG file was not created")
        return False


def build_img_file(changeset_name, source_efi, paths):
    """Build a 50MB .img file with EFI partition"""
    
    img_filename = f'opencore-{changeset_name}.img'
    img_path = paths['out'] / img_filename
    
    log(f"Creating 50MB disk image: {img_filename}")
    
    # Remove existing img file and any .dmg file
    if img_path.exists():
        img_path.unlink()
    dmg_path = paths['out'] / f'{img_filename}.dmg'
    if dmg_path.exists():
        dmg_path.unlink()
    
    if sys.platform == 'darwin':
        # macOS approach using hdiutil
        log("Creating disk image with hdiutil...")
        
        # Create a 50MB disk image with MBR partition table and FAT32 filesystem
        # Note: hdiutil will append .dmg automatically, so we create without .img extension
        temp_name = f'opencore-{changeset_name}'
        temp_path = paths['out'] / temp_name
        
        cmd = f'hdiutil create -size 50m -fs MS-DOS -volname "OZZY-OC" -layout MBRSPUD "{temp_path}"'
        if not run_command(cmd, "Creating disk image"):
            return False
        
        # hdiutil creates temp_name.dmg, so rename it to .img
        created_dmg = paths['out'] / f'{temp_name}.dmg'
        if created_dmg.exists():
            created_dmg.rename(img_path)
            log(f"Renamed {created_dmg.name} to {img_path.name}")
        else:
            error(f"Expected DMG file not found: {created_dmg}")
            return False
        
        # Mount the image
        log("Mounting disk image...")
        result = subprocess.run(['hdiutil', 'attach', str(img_path)], 
                              capture_output=True, text=True)
        if result.returncode != 0:
            error(f"Failed to attach disk image: {result.stderr}")
            return False
        
        mount_point = "/Volumes/OZZY-OC"
        
        try:
            # Copy EFI structure
            log("Copying EFI structure to disk image...")
            if not run_command(f'cp -R "{source_efi}" "{mount_point}/"', "Copying EFI files"):
                return False
                
            # Ensure proper permissions
            if not run_command(f'chmod -R 755 "{mount_point}/EFI"', "Setting permissions"):
                return False
                
        finally:
            # Unmount
            log("Unmounting disk image...")
            subprocess.run(['hdiutil', 'detach', mount_point], 
                          capture_output=True, check=False)
    
    else:
        # Linux approach - create raw image with dd and format
        log("Creating 50MB raw disk image...")
        if not run_command(f'dd if=/dev/zero of="{img_path}" bs=1m count=50', "Creating disk image"):
            return False
        
        # Format as FAT32 with EFI label
        log("Formatting disk image as FAT32...")
        if not run_command(f'mkfs.fat -F 32 -n "OZZY-OC" "{img_path}"', "Formatting disk image"):
            return False
        
        # Mount and copy EFI files
        log("Mounting disk image and copying EFI files...")
        import tempfile
        
        with tempfile.TemporaryDirectory() as temp_mount:
            # Mount the image
            if not run_command(f'sudo mount -o loop "{img_path}" "{temp_mount}"', "Mounting disk image"):
                return False
            
            try:
                # Copy EFI structure
                log("Copying EFI structure to disk image...")
                if not run_command(f'sudo cp -R "{source_efi}"/* "{temp_mount}/"', "Copying EFI files"):
                    return False
                    
                # Ensure proper permissions
                if not run_command(f'sudo chmod -R 755 "{temp_mount}/EFI"', "Setting permissions"):
                    return False
                    
            finally:
                # Unmount
                log("Unmounting disk image...")
                subprocess.run(['sudo', 'umount', temp_mount], 
                              capture_output=True, check=False)
    
    log(f"✓ OpenCore IMG built successfully: {img_path}")
    return True


def main():
    parser = argparse.ArgumentParser(description='Build OpenCore IMG (disk image)')
    parser.add_argument('changeset', help='Changeset name (without .yaml)')
    parser.add_argument('--force', '-f', action='store_true', help='Force rebuild (clean first)')
    parser.add_argument('--no-validate', action='store_true', help='Skip validation before building')

    args = parser.parse_args()

    try:
        if build_opencore_img(changeset_name=args.changeset, force_rebuild=args.force, no_validate=args.no_validate):
            log("IMG build completed successfully!")
            return 0
        else:
            error("IMG build failed")
            return 1
    except KeyboardInterrupt:
        warn("Build cancelled by user")
        return 1
    except Exception as e:
        error(f"Build failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
