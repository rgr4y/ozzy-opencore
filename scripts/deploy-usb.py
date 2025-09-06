#!/usr/bin/env python3.11
"""
Deploy EFI structure to USB Install volume automatically.

This script automatically detects macOS Install volumes in /Volumes/Install*
and deploys the built EFI structure to the EFI partition on the same disk.
"""

import sys
import subprocess
import glob
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from common import log, warn, error, info, run_command, get_project_paths

def find_install_volumes():
    """Find all Install volumes in /Volumes/"""
    install_volumes = []
    volumes_pattern = "/Volumes/Install*"
    
    log("Scanning for Install volumes...")
    
    for volume_path in glob.glob(volumes_pattern):
        volume = Path(volume_path)
        if volume.exists() and volume.is_dir():
            log(f"Found Install volume: {volume}")
            install_volumes.append(volume)
    
    return install_volumes

def get_disk_identifier(volume_path):
    """Get disk identifier for a volume using diskutil"""
    try:
        result = subprocess.run(['diskutil', 'info', str(volume_path)], 
                              capture_output=True, text=True, check=True)
        
        for line in result.stdout.split('\n'):
            if 'Device Identifier:' in line:
                disk_id = line.split(':')[1].strip()
                return disk_id
    except subprocess.CalledProcessError as e:
        error(f"Failed to get disk info for {volume_path}: {e.stderr}")
        return None
    except Exception as e:
        error(f"Error getting disk identifier: {e}")
        return None

def check_efi_partition_exists(base_disk):
    """Check if EFI partition exists on the disk"""
    efi_disk_id = f"{base_disk}s1"  # EFI is usually partition 1
    
    try:
        result = subprocess.run(['diskutil', 'info', efi_disk_id], 
                              capture_output=True, text=True, check=True)
        
        # Check if it's actually an EFI partition
        for line in result.stdout.split('\n'):
            if 'File System Personality:' in line and 'FAT32' in line:
                return True
            if 'Volume Name:' in line and 'EFI' in line:
                return True
        return False
    except subprocess.CalledProcessError:
        return False

def mount_efi_partition(base_disk):
    """Mount the EFI partition and return the mount point"""
    efi_disk_id = f"{base_disk}s1"
    
    try:
        # Try to mount the EFI partition
        result = subprocess.run(['sudo', 'diskutil', 'mount', efi_disk_id],
                              capture_output=True, text=True, check=True)
        
        # EFI partition typically mounts to /Volumes/EFI
        efi_mount_point = Path("/Volumes/EFI")
        if efi_mount_point.exists():
            log(f"EFI partition mounted at: {efi_mount_point}")
            return efi_mount_point
        else:
            error("EFI partition mounted but /Volumes/EFI not found")
            return None
            
    except subprocess.CalledProcessError as e:
        error(f"Failed to mount EFI partition {efi_disk_id}: {e.stderr}")
        return None

def deploy_efi_to_usb(source_efi_path, efi_mount_point):
    """Deploy EFI structure to USB EFI partition"""
    target_efi_path = efi_mount_point / "EFI"
    
    # Remove existing EFI folder if it exists
    if target_efi_path.exists():
        log(f"Removing existing EFI folder: {target_efi_path}")
        run_command(f'rm -rf "{target_efi_path}"')
    
    # Copy the EFI structure
    log(f"Copying EFI structure to USB...")
    run_command(f'cp -R "{source_efi_path}" "{target_efi_path}"')
    
    # Verify critical files
    bootx64_path = target_efi_path / "BOOT" / "BOOTx64.efi"
    opencore_path = target_efi_path / "OC" / "OpenCore.efi"
    config_path = target_efi_path / "OC" / "config.plist"
    
    if all(p.exists() for p in [bootx64_path, opencore_path, config_path]):
        log("✓ Critical EFI files verified on USB")
        return True
    else:
        error("✗ Missing critical EFI files on USB")
        return False

def main():
    """Main deployment function"""
    log("Starting USB EFI deployment...")
    
    # Get project paths
    paths = get_project_paths()
    source_efi_path = paths['usb_efi'] / "EFI"
    
    # Check if source EFI structure exists
    if not source_efi_path.exists():
        error(f"Source EFI structure not found: {source_efi_path}")
        error("Please run the full USB workflow first to build the EFI structure")
        sys.exit(1)
    
    # Find Install volumes
    install_volumes = find_install_volumes()
    
    if not install_volumes:
        log("Install USB not found -- either plug it in and try again, or check if EFI partition exists")
        sys.exit(0)  # Exit successfully but with message
    
    if len(install_volumes) > 1:
        warn("Multiple Install volumes found:")
        for i, volume in enumerate(install_volumes, 1):
            warn(f"  {i}. {volume}")
        warn("Using the first one found")
    
    # Use the first Install volume
    install_volume = install_volumes[0]
    log(f"Using Install volume: {install_volume}")
    
    # Get disk identifier
    disk_id = get_disk_identifier(install_volume)
    if not disk_id:
        error("Could not determine disk identifier")
        sys.exit(1)
    
    # Extract base disk (e.g., disk2s2 -> disk2)
    base_disk = disk_id.rsplit('s', 1)[0]
    log(f"Base disk: {base_disk}")
    
    # Check if EFI partition exists
    if not check_efi_partition_exists(base_disk):
        log("Install USB not found -- either plug it in and try again, or check if EFI partition exists")
        sys.exit(0)  # Exit successfully but with message
    
    # Mount EFI partition
    efi_mount_point = mount_efi_partition(base_disk)
    if not efi_mount_point:
        error("Failed to mount EFI partition")
        sys.exit(1)
    
    # Deploy EFI structure
    if deploy_efi_to_usb(source_efi_path, efi_mount_point):
        log("🎉 EFI deployment to USB completed successfully!")
        info(f"Your USB is ready to boot with the deployed configuration")
        info(f"EFI deployed to: {efi_mount_point / 'EFI'}")
    else:
        error("EFI deployment failed")
        sys.exit(1)

if __name__ == "__main__":
    main()
