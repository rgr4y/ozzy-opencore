#!/usr/bin/env python3.11

import os
import sys
import subprocess
import argparse
import shutil
import yaml
from pathlib import Path

# Add lib directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from paths import paths

def load_config():
    """Load configuration from deploy.env file"""
    env_file = paths.config / 'deploy.env'
    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Remove quotes if present
                        value = value.strip('"\'')
                        os.environ[key.strip()] = value
        except Exception as e:
            print(f"[!] Warning: Could not load {env_file}: {e}")
    else:
        print(f"[!] Warning: {env_file} not found, using defaults")

def run(cmd: str):
    """Execute a local command"""
    print(f'[+] {cmd}')
    subprocess.check_call(cmd, shell=True)

def cleanup_macos_metadata(directory):
    """Remove macOS metadata files recursively"""
    count = 0
    for root, dirs, files in os.walk(directory):
        # Remove ._* files
        for file in files[:]:  # Use slice copy to modify during iteration
            if file.startswith('._'):
                file_path = os.path.join(root, file)
                os.remove(file_path)
                count += 1
        # Remove __MACOSX directories
        for dir_name in dirs[:]:  # Use slice copy to modify during iteration
            if dir_name == '__MACOSX':
                dir_path = os.path.join(root, dir_name)
                shutil.rmtree(dir_path)
                dirs.remove(dir_name)
                count += 1
    if count > 0:
        print(f"[✓] Removed {count} macOS metadata files/directories")

def validate_required_kexts(changeset_file, output_dir):
    """Validate that all kexts specified in changeset are present"""
    try:
        with open(changeset_file, 'r') as f:
            changeset = yaml.safe_load(f)
        
        kexts = changeset.get('kexts', [])
        if not kexts:
            print("[*] No kexts specified in changeset")
            return
        
        kexts_dir = output_dir / "EFI" / "OC" / "Kexts"
        missing_kexts = []
        found_kexts = []
        
        for kext in kexts:
            kext_name = kext.get('bundle', '')
            if kext_name:
                kext_path = kexts_dir / kext_name
                info_plist = kext_path / "Contents" / "Info.plist"
                
                if kext_path.exists() and info_plist.exists():
                    found_kexts.append(kext_name)
                else:
                    missing_kexts.append(kext_name)
        
        print(f"[*] Kext validation: {len(found_kexts)}/{len(kexts)} kexts found")
        for kext_name in found_kexts:
            print(f"[✓] {kext_name}")
        
        if missing_kexts:
            print(f"[!] Missing kexts:")
            for kext_name in missing_kexts:
                print(f"[✗] {kext_name}")
            raise SystemExit(f"Missing required kexts: {', '.join(missing_kexts)}")
            
    except yaml.YAMLError as e:
        print(f"[!] Error reading changeset file: {e}")
    except Exception as e:
        print(f"[!] Error validating kexts: {e}")

def create_usb_efi(changeset_name=None, output_dir=None, force_rebuild=False, dry_run=False, usb_path=None, skip_smbios_generation=False):
    """Create USB-ready EFI structure"""
    
    load_config()
    
    # Set default output directory
    if not output_dir:
        output_dir = paths.usb_build
    else:
        output_dir = Path(output_dir)
    
    if dry_run:
        print(f"[DRY RUN] Would create USB EFI structure in: {output_dir}")
        if usb_path:
            print(f"[DRY RUN] Would copy to USB drive: {usb_path}")
    else:
        print(f"[*] Creating USB EFI structure in: {output_dir}")
    
    # If rebuilding, fetch assets first if they don't exist
    if force_rebuild:
        if not paths.ocvalidate.exists():
            if dry_run:
                print("[DRY RUN] Would fetch OpenCore assets for rebuild...")
            else:
                print("[*] Fetching OpenCore assets for rebuild...")
                fetch_script = paths.bin / "fetch_assets.sh"
                if fetch_script.exists():
                    run(f'bash "{fetch_script}"')
                else:
                    print("[!] ERROR: fetch_assets.sh not found")
                    raise SystemExit("Cannot fetch assets for rebuild")
    
    # Apply changeset if specified
    changeset_data = None
    if changeset_name:
        changeset_file = paths.changeset_file(changeset_name)
        if not changeset_file.exists():
            raise SystemExit(f'Changeset not found: {changeset_file}')
        
        if dry_run:
            print(f"[DRY RUN] Would load changeset: {changeset_name}")
            # Load changeset data for dry run analysis
            with open(changeset_file, 'r') as f:
                changeset_data = yaml.safe_load(f)
            
            # Check SMBIOS status for dry run
            if not skip_smbios_generation:
                print("[DRY RUN] Would validate SMBIOS configuration...")
                if 'smbios' in changeset_data:
                    smbios = changeset_data['smbios']
                    serial = smbios.get('SystemSerialNumber', '')
                    mlb = smbios.get('MLB', '')
                    uuid_str = smbios.get('SystemUUID', '')
                    
                    # Import validation functions for dry run
                    sys.path.append(str(ROOT / "scripts"))
                    try:
                        from generate_smbios import is_placeholder_serial, is_placeholder_mlb, is_placeholder_uuid
                        
                        needs_generation = (is_placeholder_serial(serial) or 
                                          is_placeholder_mlb(mlb) or 
                                          is_placeholder_uuid(uuid_str))
                        
                        if needs_generation:
                            print(f"[DRY RUN] Would generate new SMBIOS data (placeholders detected)")
                            print(f"[DRY RUN]   Current Serial: {serial}")
                            print(f"[DRY RUN]   Current MLB: {mlb}")
                            print(f"[DRY RUN]   Current UUID: {uuid_str}")
                        else:
                            print(f"[DRY RUN] SMBIOS data appears valid (no generation needed)")
                    except ImportError:
                        print("[DRY RUN] Would check SMBIOS validation...")
                else:
                    print("[DRY RUN] No SMBIOS configuration found in changeset")
            else:
                print("[DRY RUN] Would skip SMBIOS generation (--skip-smbios-generation flag set)")
        else:
            # Load changeset data
            with open(changeset_file, 'r') as f:
                changeset_data = yaml.safe_load(f)
            
            # Validate and generate SMBIOS if needed (unless skipped)
            if not skip_smbios_generation:
                print("[*] Validating SMBIOS configuration...")
                smbios_script = paths.scripts / "generate_smbios.py"
                if smbios_script.exists():
                    smbios_cmd = [sys.executable, str(smbios_script), str(changeset_file)]
                    try:
                        subprocess.check_call(smbios_cmd)
                        # Reload changeset after potential SMBIOS updates
                        with open(changeset_file, 'r') as f:
                            changeset_data = yaml.safe_load(f)
                    except subprocess.CalledProcessError:
                        print("[!] WARNING: SMBIOS validation failed, continuing with existing values")
            else:
                print("[*] Skipping SMBIOS generation (--skip-smbios-generation flag set)")
            
            print(f"[*] Applying changeset: {changeset_name}")
            # Use the same Python interpreter that's running this script
            cmd = [sys.executable, str(paths.scripts / "apply_changeset.py"), str(changeset_file)]
            print(f'[+] {" ".join(cmd)}')
            subprocess.check_call(cmd)
            
            # Validate the configuration
            if paths.ocvalidate.exists():
                print("[*] Validating OpenCore configuration...")
                run(f'bash "{paths.validation_script}"')
            else:
                print("[!] WARNING: ocvalidate not found - skipping validation")
    
    # Create USB EFI directory structure
    efi_source = paths.efi_build
    if not efi_source.exists():
        raise SystemExit(f"EFI build directory not found: {efi_source}")
    
    if dry_run:
        print(f"[DRY RUN] Would copy EFI structure from: {efi_source}")
        print(f"[DRY RUN] Would create directory: {output_dir}")
        
        # Show what would be copied
        if efi_source.exists():
            print(f"[DRY RUN] Files that would be copied:")
            file_count = 0
            for item in efi_source.rglob('*'):
                if item.is_file():
                    rel_path = item.relative_to(efi_source)
                    file_size = item.stat().st_size
                    size_str = f"({file_size:,} bytes)" if file_size > 0 else "(empty)"
                    print(f"[DRY RUN]   {rel_path} {size_str}")
                    file_count += 1
            print(f"[DRY RUN] Total files to copy: {file_count}")
        else:
            print(f"[DRY RUN] ERROR: Source directory does not exist: {efi_source}")
    else:
        # Remove existing output directory if it exists
        if output_dir.exists():
            print(f"[*] Removing existing directory: {output_dir}")
            shutil.rmtree(output_dir)
        
        # Copy EFI structure to output directory
        print(f"[*] Copying EFI structure to: {output_dir}")
        shutil.copytree(efi_source, output_dir)
        
        # Clean up macOS metadata files after copy
        print("[*] Cleaning up macOS metadata files...")
        cleanup_macos_metadata(output_dir)
        
        # Validate that all specified kexts are present
        if changeset_name:
            changeset_file = ROOT / "config" / "changesets" / f"{changeset_name}.yaml"
            if changeset_file.exists():
                validate_required_kexts(changeset_file, output_dir)
    
    # Check for required drivers and copy from OpenCore assets if needed
    drivers_dir = output_dir / "EFI" / "OC" / "Drivers"
    required_drivers = ["HfsPlus.efi", "OpenCanopy.efi"]
    
    if dry_run:
        print(f"[DRY RUN] Would check for required drivers in: {drivers_dir}")
        for driver_file in required_drivers:
            driver_path = drivers_dir / driver_file
            if not driver_path.exists():
                oc_driver_path = ROOT / "out" / "opencore" / "X64" / "EFI" / "OC" / "Drivers" / driver_file
                if oc_driver_path.exists():
                    file_size = oc_driver_path.stat().st_size
                    size_str = f"({file_size:,} bytes)" if file_size > 0 else "(empty)"
                    print(f"[DRY RUN]   Would copy driver: {driver_file} from {oc_driver_path} {size_str}")
                else:
                    print(f"[DRY RUN]   WARNING: Driver not available: {driver_file} (source: {oc_driver_path})")
    else:
        # Copy additional drivers if needed
        for driver_file in required_drivers:
            driver_path = drivers_dir / driver_file
            if not driver_path.exists():
                print(f"[*] Driver missing: {driver_file}")
                # Try to get from OpenCore assets
                oc_driver_path = ROOT / "out" / "opencore" / "X64" / "EFI" / "OC" / "Drivers" / driver_file
                if oc_driver_path.exists():
                    print(f"[*] Copying from OpenCore assets: {driver_file}")
                    shutil.copy2(oc_driver_path, driver_path)
                else:
                    print(f"[!] WARNING: {driver_file} not found in OpenCore assets")
    
    # Check for required ACPI files
    acpi_dir = output_dir / "EFI" / "OC" / "ACPI"
    required_acpi = ["SSDT-EC-USBX.aml", "SSDT-AWAC-DISABLE.aml"]
    
    if dry_run:
        print(f"[DRY RUN] Would check for required ACPI files in: {acpi_dir}")
        for acpi_file in required_acpi:
            sample_path = ROOT / "out" / "opencore" / "Docs" / "AcpiSamples" / "Binaries" / acpi_file
            if sample_path.exists():
                file_size = sample_path.stat().st_size
                size_str = f"({file_size:,} bytes)" if file_size > 0 else "(empty)"
                print(f"[DRY RUN]   Would copy ACPI file: {acpi_file} from {sample_path} {size_str}")
            else:
                print(f"[DRY RUN]   WARNING: ACPI file not available: {acpi_file} (source: {sample_path})")
    else:
        # Download additional ACPI files if needed
        for acpi_file in required_acpi:
            acpi_path = acpi_dir / acpi_file
            if not acpi_path.exists():
                print(f"[*] ACPI file missing: {acpi_file}")
                # Try to get from OpenCore sample
                sample_path = ROOT / "out" / "opencore" / "Docs" / "AcpiSamples" / "Binaries" / acpi_file
                if sample_path.exists():
                    print(f"[*] Copying from OpenCore samples: {acpi_file}")
                    shutil.copy2(sample_path, acpi_path)
                else:
                    print(f"[!] WARNING: {acpi_file} not found in samples")
    
    # Handle USB drive deployment
    if usb_path:
        usb_drive = Path(usb_path)
        
        # For USB deployment, we need to find and mount the EFI partition
        # The usb_path should point to the installer volume, but we need the EFI partition
        efi_partition_path = None
        
        if dry_run:
            print(f"[DRY RUN] USB drive deployment:")
            print(f"[DRY RUN]   Installer volume: {usb_drive}")
            print(f"[DRY RUN]   Would detect EFI partition automatically")
            print(f"[DRY RUN]   Would mount EFI partition if not already mounted")
            print(f"[DRY RUN]   Would copy EFI folder to: /Volumes/EFI/EFI/")
        else:
            print(f"[*] USB drive deployment:")
            print(f"[*]   Installer volume: {usb_drive}")
            
            # Get the disk identifier from the installer volume
            try:
                # Run diskutil to get disk info for the installer volume
                result = subprocess.run(['diskutil', 'info', str(usb_drive)], 
                                      capture_output=True, text=True)
                if result.returncode == 0:
                    # Extract disk identifier (e.g., disk2s2)
                    for line in result.stdout.split('\\n'):
                        if 'Device Identifier:' in line:
                            disk_id = line.split(':')[1].strip()
                            # Convert disk2s2 to disk2s1 (EFI partition is usually s1)
                            base_disk = disk_id.rsplit('s', 1)[0]  # disk2
                            efi_disk_id = f"{base_disk}s1"  # disk2s1
                            print(f"[*]   Detected EFI partition: {efi_disk_id}")
                            
                            # Mount the EFI partition
                            mount_result = subprocess.run(['sudo', 'diskutil', 'mount', efi_disk_id],
                                                        capture_output=True, text=True)
                            if mount_result.returncode == 0:
                                efi_partition_path = Path("/Volumes/EFI")
                                print(f"[*]   EFI partition mounted at: {efi_partition_path}")
                            else:
                                print(f"[!]   Failed to mount EFI partition: {mount_result.stderr}")
                            break
                else:
                    print(f"[!]   Failed to get disk info: {result.stderr}")
            except Exception as e:
                print(f"[!]   Error detecting EFI partition: {e}")
            
            if efi_partition_path and efi_partition_path.exists():
                usb_efi_path = efi_partition_path / "EFI"
                
                if usb_efi_path.exists():
                    print(f"[*] Removing existing EFI folder on USB EFI partition: {usb_efi_path}")
                    shutil.rmtree(usb_efi_path)
                
                print(f"[*] Copying EFI folder to USB EFI partition...")
                shutil.copytree(output_dir / "EFI", usb_efi_path)
                print(f"[✓] EFI deployed to USB EFI partition: {usb_efi_path}")
                
                # Verify the structure
                bootx64_path = usb_efi_path / "BOOT" / "BOOTx64.efi"
                opencore_path = usb_efi_path / "OC" / "OpenCore.efi"
                if bootx64_path.exists() and opencore_path.exists():
                    print(f"[✓] Critical bootloaders verified on EFI partition")
                else:
                    print(f"[!] WARNING: Missing critical bootloaders on EFI partition")
            else:
                print(f"[!] ERROR: Could not access EFI partition")
                print(f"[!] Please manually mount the EFI partition and copy the EFI folder")
                return
    
    # Create a deployment summary
    summary_file = output_dir / "DEPLOYMENT_INFO.txt"
    
    if dry_run:
        print(f"[DRY RUN] Would create deployment summary: {summary_file}")
    else:
        with open(summary_file, 'w') as f:
            f.write(f"OpenCore USB EFI Deployment - Bare Metal\\n")
            f.write(f"Generated: {subprocess.check_output(['date'], text=True).strip()}\\n")
            f.write(f"Changeset: {changeset_name or 'None'}\\n")
            f.write(f"Target: Crosshair VIII Hero + Ryzen 3950X + RX580\\n")
            f.write(f"\\n")
            f.write(f"EFI Structure (ready for USB):\\n")
            f.write(f"EFI/\\n")
            f.write(f"├── BOOT/\\n")
            f.write(f"│   └── BOOTx64.efi              # UEFI bootloader\\n")
            f.write(f"└── OC/\\n")
            f.write(f"    ├── ACPI/\\n")
            f.write(f"    │   ├── SSDT-EC-USBX.aml     # USB & EC fix\\n")
            f.write(f"    │   └── SSDT-AWAC-DISABLE.aml # System clock fix\\n")
            f.write(f"    ├── Drivers/\\n")
            f.write(f"    │   ├── OpenRuntime.efi      # Required\\n")
            f.write(f"    │   ├── HfsPlus.efi      # HFS+ support\\n")
            f.write(f"    │   └── OpenCanopy.efi       # GUI picker\\n")
            f.write(f"    ├── Kexts/\\n")
            f.write(f"    │   ├── Lilu.kext            # Patching engine\\n")
            f.write(f"    │   ├── WhateverGreen.kext   # GPU patches\\n")
            f.write(f"    │   ├── VirtualSMC.kext      # SMC emulation\\n")
            f.write(f"    │   └── AppleMCEReporterDisabler.kext  # AMD fix\\n")
            f.write(f"    ├── Tools/\\n")
            f.write(f"    │   ├── OpenShell.efi        # UEFI Shell\\n")
            f.write(f"    │   └── ResetNvramEntry.efi  # NVRAM reset\\n")
            f.write(f"    ├── config.plist             # Main config\\n")
            f.write(f"    └── OpenCore.efi             # OpenCore loader\\n")
            f.write(f"\\n")
            f.write(f"USB Deployment Steps:\\n")
            f.write(f"1. USB stick should have been created with createinstallmedia\\n")
            f.write(f"2. Mount the USB's EFI partition: sudo diskutil mount disk2s1\\n")
            f.write(f"3. Copy EFI folder to /Volumes/EFI/EFI/ (NOT the installer volume!)\\n")
            f.write(f"4. Verify structure: /Volumes/EFI/EFI/BOOT/BOOTx64.efi exists\\n")
            f.write(f"5. Set BIOS to UEFI boot mode and disable Secure Boot\\n")
            f.write(f"6. Boot from USB - firmware will find BOOTx64.efi on EFI partition\\n")
            f.write(f"7. OpenCore will chain-load the Sequoia installer from second partition\\n")
            f.write(f"8. After install, mount target drive's EFI and copy EFI folder there\\n")
            f.write(f"\\n")
            f.write(f"Configuration Highlights:\\n")
            f.write(f"- SMBIOS: iMacPro1,1 (optimal for AMD + RX580)\\n")
            f.write(f"- Boot Args: agdpmod=pikera keepsyms=1 debug=0x100\\n")
            f.write(f"- XhciPortLimit: YES (for initial install)\\n")
            f.write(f"- ProvideCurrentCpuInfo: YES (AMD requirement)\\n")
            f.write(f"- DummyPowerManagement: YES (AMD requirement)\\n")
            f.write(f"- SIP: Enabled (00000000) for install\\n")
    
    if dry_run:
        print(f"[DRY RUN] ✓ USB EFI structure would be created successfully!")
        print(f"[DRY RUN] Location: {output_dir}")
        if usb_path:
            print(f"[DRY RUN] USB deployment: {usb_path}/EFI")
        
        # Show changeset analysis
        if changeset_data and 'smbios' in changeset_data:
            smbios = changeset_data['smbios']
            print(f"[DRY RUN] SMBIOS Configuration:")
            print(f"[DRY RUN]   Model: {smbios.get('SystemProductName', 'Not set')}")
            print(f"[DRY RUN]   Serial: {smbios.get('SystemSerialNumber', 'Not set')}")
            print(f"[DRY RUN]   MLB: {smbios.get('MLB', 'Not set')}")
            print(f"[DRY RUN]   UUID: {smbios.get('SystemUUID', 'Not set')}")
        
        print(f"[DRY RUN] No files were modified. Use --execute to perform actual deployment.")
    else:
        print(f"[✓] USB EFI structure created successfully!")
        print(f"[i] Location: {output_dir}")
        if usb_path:
            print(f"[i] Deployed to USB EFI partition: /Volumes/EFI/EFI/")
        print(f"[i] Deployment info saved to: {summary_file}")
        
        # List key files for verification
        print(f"\\n[*] Key files verification:")
        key_files = [
            "EFI/BOOT/BOOTx64.efi",
            "EFI/OC/OpenCore.efi", 
            "EFI/OC/config.plist",
            "EFI/OC/Drivers/OpenRuntime.efi",
            "EFI/OC/Drivers/HfsPlus.efi",
            "EFI/OC/Kexts/Lilu.kext",
            "EFI/OC/Kexts/WhateverGreen.kext",
            "EFI/OC/ACPI/SSDT-EC-USBX.aml"
        ]
        
        for file_path in key_files:
            full_path = output_dir / file_path
            status = "✓" if full_path.exists() else "✗"
            print(f"    {status} {file_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Create USB-ready OpenCore EFI structure')
    parser.add_argument('--changeset', help='Apply named changeset configuration')
    parser.add_argument('--output', help='Output directory for USB EFI structure')
    parser.add_argument('--rebuild', action='store_true', help='Force rebuild and fetch assets')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be done without making changes')
    parser.add_argument('--usb', help='Path to USB drive for direct deployment')
    parser.add_argument('--skip-smbios-generation', action='store_true', 
                       help='Skip automatic SMBIOS generation (use if you already generated serials separately)')
    
    args = parser.parse_args()
    
    try:
        create_usb_efi(
            changeset_name=args.changeset,
            output_dir=args.output,
            force_rebuild=args.rebuild,
            dry_run=args.dry_run,
            usb_path=args.usb,
            skip_smbios_generation=args.skip_smbios_generation
        )
    except KeyboardInterrupt:
        print("\\n[!] Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\\n[!] USB EFI creation failed: {e}")
        sys.exit(1)
