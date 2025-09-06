#!/usr/bin/env python3.11
"""
Full USB Workflow

Apply changeset → Build ISO → Create USB structure in one command.
This is one of the main workflows requested by the user.
"""

import sys
import subprocess
import argparse
import glob
import os
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import ROOT, log, warn, error, info, run_command
import yaml

def populate_efi_assets(changeset_name):
    """Populate EFI directory structure with kexts, drivers, tools, and ACPI files"""
    
    # Load the changeset to see what assets we need
    changeset_path = ROOT / "config" / "changesets" / f"{changeset_name}.yaml"
    with open(changeset_path, 'r') as f:
        changeset_data = yaml.safe_load(f)
    
    efi_base = ROOT / "out" / "efi" / "EFI"
    oc_dir = efi_base / "OC"
    
    # Ensure directories exist and clean up any old kext files
    (oc_dir / "Kexts").mkdir(parents=True, exist_ok=True)
    (oc_dir / "Drivers").mkdir(parents=True, exist_ok=True)
    (oc_dir / "Tools").mkdir(parents=True, exist_ok=True)
    (oc_dir / "ACPI").mkdir(parents=True, exist_ok=True)
    (efi_base / "BOOT").mkdir(parents=True, exist_ok=True)
    
    # Clean up existing kext directory to ensure only changeset kexts are present
    import shutil
    kexts_dir = oc_dir / "Kexts"
    if kexts_dir.exists():
        shutil.rmtree(kexts_dir)
    kexts_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy kexts
    if 'kexts' in changeset_data:
        log("Copying kexts...")
        for kext in changeset_data['kexts']:
            kext_name = kext['bundle']
            # Look for kext in various possible locations
            source_locations = [
                ROOT / "out" / f"kext-release-acidanthera_{kext_name.replace('.kext', '')}" / kext_name,
                ROOT / "out" / f"kext-release-acidanthera_{kext_name.replace('.kext', '')}" / "Kexts" / kext_name,  # VirtualSMC layout
                ROOT / "out" / f"kext-{kext_name.replace('.kext', '')}" / kext_name,
                ROOT / "assets" / kext_name
            ]
            
            # Special handling for AppleMCEReporterDisabler.kext zip file
            if kext_name == "AppleMCEReporterDisabler.kext":
                zip_path = ROOT / "assets" / "AppleMCEReporterDisabler.kext.zip"
                if zip_path.exists():
                    # Extract the zip to a temporary location
                    import zipfile
                    temp_extract_path = ROOT / "out" / "temp_kext_extract"
                    temp_extract_path.mkdir(exist_ok=True)
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(temp_extract_path)
                    extracted_kext = temp_extract_path / kext_name
                    if extracted_kext.exists():
                        source_locations.insert(0, extracted_kext)  # Add as first priority
            
            source_kext = None
            for location in source_locations:
                if location.exists():
                    source_kext = location
                    break
            
            if source_kext:
                target_kext = oc_dir / "Kexts" / kext_name
                run_command(f'rsync -av --delete "{source_kext}/" "{target_kext}/"', f"Copying {kext_name}")
            else:
                warn(f"Kext not found: {kext_name} (searched in {len(source_locations)} locations)")
    
    # Copy drivers
    if 'uefi_drivers' in changeset_data:
        log("Copying UEFI drivers...")
        for driver in changeset_data['uefi_drivers']:
            driver_name = driver['path']
            # Look for drivers in various locations
            source_locations = [
                ROOT / "out" / "opencore" / "X64" / "EFI" / "OC" / "Drivers" / driver_name,
                ROOT / "out" / "ocbinarydata-repo" / "Drivers" / driver_name,
                ROOT / "out" / "opencore" / "Drivers" / driver_name,
            ]
            
            source_driver = None
            for location in source_locations:
                if location.exists():
                    source_driver = location
                    break
                    
            if source_driver:
                target_driver = oc_dir / "Drivers" / driver_name
                run_command(f'cp "{source_driver}" "{target_driver}"', f"Copying {driver_name}")
            else:
                warn(f"Driver not found: {driver_name}")

    # Copy tools
    if 'tools' in changeset_data:
        log("Copying tools...")
        for tool in changeset_data['tools']:
            tool_name = tool['Path']
            # Look for tools in various locations
            source_locations = [
                ROOT / "out" / "opencore" / "X64" / "EFI" / "OC" / "Tools" / tool_name,
                ROOT / "out" / "opencore" / "X64" / "EFI" / "OC" / "Drivers" / tool_name,  # Some tools are in Drivers
                ROOT / "out" / "opencore" / "Tools" / tool_name,
            ]
            
            source_tool = None
            for location in source_locations:
                if location.exists():
                    source_tool = location
                    break
                    
            if source_tool:
                target_tool = oc_dir / "Tools" / tool_name
                run_command(f'cp "{source_tool}" "{target_tool}"', f"Copying {tool_name}")
            else:
                warn(f"Tool not found: {tool_name}")    # Copy ACPI files
    if 'acpi_add' in changeset_data:
        log("Copying ACPI files...")
        for acpi_file in changeset_data['acpi_add']:
            # Look for ACPI files in multiple locations
            source_locations = [
                ROOT / "assets" / acpi_file,
                ROOT / "out" / "opencore" / "Docs" / "AcpiSamples" / "Binaries" / acpi_file,
                ROOT / "out" / "opencore" / "AcpiSamples" / "Binaries" / acpi_file,
                ROOT / "out" / "acpi" / acpi_file
            ]
            
            source_acpi = None
            for location in source_locations:
                if location.exists():
                    source_acpi = location
                    break
            
            if source_acpi:
                target_acpi = oc_dir / "ACPI" / acpi_file
                run_command(f'cp "{source_acpi}" "{target_acpi}"', f"Copying {acpi_file}")
            else:
                warn(f"ACPI file not found: {acpi_file} (searched in {len(source_locations)} locations)")
    
    # Copy OpenCore bootloader files correctly
    log("Copying OpenCore bootloader...")
    
    # Copy the proper UEFI boot stub (BOOTx64.efi) 
    bootx64_source = ROOT / "out" / "opencore" / "X64" / "EFI" / "BOOT" / "BOOTx64.efi"
    target_bootloader = efi_base / "BOOT" / "BOOTx64.efi"
    
    if bootx64_source.exists():
        run_command(f'cp "{bootx64_source}" "{target_bootloader}"', "Copying OpenCore bootloader to BOOT")
    else:
        warn(f"BOOTx64.efi not found at {bootx64_source}")
    
    # Copy OpenCore.efi to OC directory
    opencore_source = ROOT / "out" / "opencore" / "X64" / "EFI" / "OC" / "OpenCore.efi"
    target_oc = oc_dir / "OpenCore.efi"
    
    if opencore_source.exists():
        run_command(f'cp "{opencore_source}" "{target_oc}"', "Copying OpenCore.efi to OC")
    else:
        warn(f"OpenCore.efi not found at {opencore_source}")

def full_usb_workflow(changeset_name, output_path=None, force=False, eject=False):
    """Execute the full USB workflow: changeset → ISO → USB → Deploy"""
    
    log(f"Starting full USB workflow for changeset: {changeset_name}")
    
    # Step 1: Apply changeset
    log("Step 1/4: Applying changeset...")
    apply_script = ROOT / "scripts" / "apply-changeset.py"
    changeset_path = ROOT / "config" / "changesets" / f"{changeset_name}.yaml"
    
    if not changeset_path.exists():
        error(f"Changeset not found: {changeset_path}")
        return False
    
    cmd = [sys.executable, str(apply_script), changeset_name]  # Pass just the name, not the path
    try:
        result = subprocess.run(cmd, cwd=ROOT, check=True)
        log("✓ Changeset applied successfully")
    except subprocess.CalledProcessError as e:
        error(f"Failed to apply changeset: {e}")
        return False
    
    # Step 1.5: Populate EFI structure with assets
    log("Step 1.5/4: Populating EFI structure with assets...")
    try:
        populate_efi_assets(changeset_name)
        log("✓ EFI assets populated successfully")
    except Exception as e:
        error(f"Failed to populate EFI assets: {e}")
        return False
    
    # Step 2: Build ISO
    log("Step 2/4: Building OpenCore ISO...")
    build_iso_script = ROOT / "scripts" / "build-iso.py"
    cmd = [sys.executable, str(build_iso_script)]
    if force:
        cmd.append("--force")
    
    try:
        result = subprocess.run(cmd, cwd=ROOT, check=True)
        log("✓ ISO built successfully")
    except subprocess.CalledProcessError as e:
        error(f"Failed to build ISO: {e}")
        return False
    
    # Step 3: Create USB structure
    log("Step 3/4: Creating USB EFI structure...")
    build_usb_script = ROOT / "scripts" / "build-usb.py"
    cmd = [sys.executable, str(build_usb_script), "--changeset", changeset_name]
    
    if output_path:
        cmd.extend(["--output", output_path])
    if force:
        cmd.append("--force")
    
    try:
        result = subprocess.run(cmd, cwd=ROOT, check=True)
        log("✓ USB structure created successfully")
    except subprocess.CalledProcessError as e:
        error(f"Failed to create USB structure: {e}")
        return False
    
    # Step 4: Deploy to USB (if Install volume is available)
    log("------------------------------------------------")
    log("Step 4/4: Deploying EFI to USB Install volume...")
    deploy_usb_script = ROOT / "scripts" / "deploy-usb.py"
    cmd = [sys.executable, str(deploy_usb_script)]
    
    try:
        result = subprocess.run(cmd, cwd=ROOT, check=True)
        log("✓ EFI deployed to USB successfully")
        
        # Eject volumes if requested
        if eject:
            log("Ejecting volumes...")
            try:
                # Find and eject Install volumes
                install_volumes = glob.glob("/Volumes/Install*")
                for volume in install_volumes:
                    log(f"Ejecting {volume}")
                    subprocess.run(["diskutil", "eject", volume], check=True)
                
                # Eject EFI volume if mounted
                efi_volume = "/Volumes/EFI"
                if os.path.exists(efi_volume):
                    log(f"Ejecting {efi_volume}")
                    subprocess.run(["diskutil", "eject", efi_volume], check=True)
                
                warn("✓ Volumes ejected successfully")
            except subprocess.CalledProcessError as e:
                error(f"Failed to eject some volumes: {e}")
                
    except subprocess.CalledProcessError as e:
        # Don't fail the whole workflow if USB deployment fails (USB might not be plugged in)
        warn(f"USB deployment failed (this is OK if no Install USB is connected): {e}")
        log("You can run 'python3 scripts/deploy-usb.py' manually when your Install USB is ready")
    
    info("Your USB-ready EFI structure is ready for deployment")
    log("🎉 Full USB workflow completed successfully!")
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Full USB Workflow: Apply changeset → Build ISO → Create USB → Deploy',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This workflow combines four operations in sequence:
1. Apply the specified changeset to OpenCore configuration
2. Build an OpenCore ISO from the configuration
3. Create a USB-ready EFI structure
4. Deploy the EFI structure to any connected Install USB

Example:
  python3 full-usb.py myconfig --output ./usb-output --force
        """
    )
    parser.add_argument('changeset', help='Changeset name (without .yaml extension)')
    parser.add_argument('--output', '-o', help='Output directory for USB structure')
    parser.add_argument('--force', '-f', action='store_true', help='Force rebuild/overwrite')
    parser.add_argument('--eject', action='store_true', help='Automatically eject EFI and Install volumes after deployment')
    
    args = parser.parse_args()
    
    try:
        if full_usb_workflow(args.changeset, args.output, args.force, args.eject):
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
