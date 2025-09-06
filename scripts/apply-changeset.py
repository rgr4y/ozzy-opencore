#!/usr/bin/env python3.11
"""
Refactored apply_changeset.py using common libraries.

This script applies OpenCore configuration changesets by merging them with
the base OpenCore configuration template.
"""

import sys
import argparse
import yaml
import json
import subprocess
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import (
    ROOT, log, warn, error,
    convert_data_values, CustomJSONEncoder,
    validate_file_exists
)
from lib.changeset import apply_amd_vanilla_patches_to_data, get_amd_vanilla_patch_info

# Project-specific paths
EFI = ROOT / "out" / "efi" / "EFI" / "OC"
TEMPLATE_PLIST = ROOT / "efi-template" / "EFI" / "OC" / "config.plist"
PATCHER = ROOT / "scripts" / "patch-plist.py"

def changeset_to_operations(changeset_data):
    """Convert changeset data to patch operations for patch-plist.py"""
    operations = []
    
    def ensure_bytes_for_kernel_patches(patches):
        """Ensure kernel patch binary fields are bytes objects"""
        if not isinstance(patches, list):
            return patches
            
        for patch in patches:
            if isinstance(patch, dict):
                # Convert binary fields to bytes objects
                for field in ['Find', 'Replace', 'Mask', 'ReplaceMask']:
                    if field in patch:
                        value = patch[field]
                        if isinstance(value, list):
                            # Convert list of integers to bytes
                            patch[field] = bytes(value)
                        elif isinstance(value, str):
                            # Handle hex strings if any
                            patch[field] = bytes.fromhex(value.replace(' ', ''))
                        # If already bytes, leave as is
        return patches
    
    # Handle kexts - append to Kernel.Add
    if 'kexts' in changeset_data:
        for kext in changeset_data['kexts']:
            exec_path = ""
            if kext.get('exec') and kext['exec'].strip():
                exec_path = f"Contents/MacOS/{kext['exec']}"
            
            kext_entry = {
                "BundlePath": kext['bundle'],
                "Enabled": True,
                "ExecutablePath": exec_path,
                "PlistPath": "Contents/Info.plist"
            }
            operations.append({
                "op": "append",
                "path": ["Kernel", "Add"],
                "entry": kext_entry,
                "key": "BundlePath"
            })
    
    # Handle booter quirks - merge into Booter.Quirks
    if 'booter_quirks' in changeset_data:
        operations.append({
            "op": "merge",
            "path": ["Booter", "Quirks"],
            "entries": changeset_data['booter_quirks']
        })
    
    # Handle kernel quirks - merge into Kernel.Quirks
    if 'kernel_quirks' in changeset_data:
        quirks = changeset_data['kernel_quirks'].copy()
        
        # Check for DummyPowerManagement in quirks and move it to emulate
        if 'DummyPowerManagement' in quirks:
            print("ERROR: DummyPowerManagement found in kernel_quirks but should be in Kernel.Emulate section!")
            print("Please move DummyPowerManagement from kernel_quirks to kernel_emulate in your changeset.")
            sys.exit(1)
        
        if quirks:  # Only add operation if there are remaining quirks
            operations.append({
                "op": "merge",
                "path": ["Kernel", "Quirks"],
                "entries": quirks
            })
    
    # Handle kernel emulate settings - merge into Kernel.Emulate
    if 'kernel_emulate' in changeset_data:
        operations.append({
            "op": "merge",
            "path": ["Kernel", "Emulate"],
            "entries": changeset_data['kernel_emulate']
        })
    
    # Handle kernel patches - set Kernel.Patch
    if 'kernel_patches' in changeset_data:
        # Ensure all binary fields are properly formatted as bytes
        patches = ensure_bytes_for_kernel_patches(changeset_data['kernel_patches'])
        operations.append({
            "op": "set",
            "path": ["Kernel", "Patch"],
            "value": patches
        })
    
    # Handle kernel emulate - set Kernel.Emulate
    if 'kernel_emulate' in changeset_data:
        operations.append({
            "op": "merge",
            "path": ["Kernel", "Emulate"],
            "entries": changeset_data['kernel_emulate']
        })
    
    # Handle boot args - set NVRAM entry
    if 'boot_args' in changeset_data:
        operations.append({
            "op": "set",
            "path": ["NVRAM", "Add", "7C436110-AB2A-4BBB-A880-FE41995C9F82", "boot-args"],
            "value": changeset_data['boot_args']
        })
    
    # Handle CSR config - set NVRAM entry
    if 'csr_active_config' in changeset_data:
        # Convert hex string to bytes
        csr_hex = changeset_data['csr_active_config']
        if isinstance(csr_hex, str):
            # Remove any spaces and convert pairs of hex chars to bytes
            csr_clean = csr_hex.replace(' ', '')
            csr_bytes = [int(csr_clean[i:i+2], 16) for i in range(0, len(csr_clean), 2)]
        else:
            csr_bytes = csr_hex
        operations.append({
            "op": "set", 
            "path": ["NVRAM", "Add", "7C436110-AB2A-4BBB-A880-FE41995C9F82", "csr-active-config"],
            "value": csr_bytes
        })
    
    # Handle SMBIOS - merge into PlatformInfo.Generic
    if 'smbios' in changeset_data:
        operations.append({
            "op": "merge",
            "path": ["PlatformInfo", "Generic"],
            "entries": changeset_data['smbios']
        })
    
    # Handle ACPI add - append to ACPI.Add
    if 'acpi_add' in changeset_data:
        for acpi_file in changeset_data['acpi_add']:
            acpi_entry = {
                "Path": acpi_file,
                "Enabled": True
            }
            operations.append({
                "op": "append",
                "path": ["ACPI", "Add"],
                "entry": acpi_entry,
                "key": "Path"
            })
    
    # Handle ACPI quirks - merge into ACPI.Quirks
    if 'acpi_quirks' in changeset_data:
        operations.append({
            "op": "merge",
            "path": ["ACPI", "Quirks"],
            "entries": changeset_data['acpi_quirks']
        })
    
    # Handle UEFI drivers - append to UEFI.Drivers
    if 'uefi_drivers' in changeset_data:
        for driver in changeset_data['uefi_drivers']:
            driver_entry = {
                "Path": driver['path'],
                "Enabled": driver.get('enabled', True),
                "LoadEarly": driver.get('load_early', False)
            }
            if 'arguments' in driver:
                driver_entry["Arguments"] = driver['arguments']
            operations.append({
                "op": "append",
                "path": ["UEFI", "Drivers"],
                "entry": driver_entry,
                "key": "Path"
            })
    
    # Handle tools - append to Misc.Tools
    if 'tools' in changeset_data:
        for tool in changeset_data['tools']:
            tool_entry = {
                "Name": tool['Name'],
                "Path": tool['Path'],
                "Enabled": tool.get('Enabled', True),
                "Auxiliary": tool.get('Auxiliary', False),
                "Arguments": "",
                "Comment": "",
                "Flavour": "Auto",
                "FullNvramAccess": False,
                "RealPath": False,
                "TextMode": False
            }
            operations.append({
                "op": "append",
                "path": ["Misc", "Tools"],
                "entry": tool_entry,
                "key": "Name"
            })
    
    # Handle device properties - merge into DeviceProperties.Add
    if 'device_properties' in changeset_data:
        operations.append({
            "op": "merge",
            "path": ["DeviceProperties", "Add"],
            "entries": changeset_data['device_properties']
        })
    
    # Handle security settings
    if 'secureboot_model' in changeset_data:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "SecureBootModel"],
            "value": changeset_data['secureboot_model']
        })
    
    if 'vault' in changeset_data:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "Vault"],
            "value": changeset_data['vault']
        })
    
    if 'scan_policy' in changeset_data:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "ScanPolicy"],
            "value": changeset_data['scan_policy']
        })
    
    return operations

def post_process_config(config_path):
    """Post-process the config.plist to fix data format issues using shell commands"""
    
    # Convert empty kernel patch arrays to proper data fields
    log("Converting kernel patch arrays to data format...")
    
    # More complex fix: convert non-empty integer arrays to base64 data for kernel patches
    log("Converting integer arrays to base64 data format...")
    
    # Python script to handle more complex conversions
    python_fix_script = f"""
import plistlib
import base64
from pathlib import Path

config_file = Path('{config_path}')
with open(config_file, 'rb') as f:
    plist_data = plistlib.load(f)

# Fix kernel patches
if 'Kernel' in plist_data and 'Patch' in plist_data['Kernel']:
    for patch in plist_data['Kernel']['Patch']:
        # Convert integer arrays to bytes for binary fields
        for field in ['Find', 'Replace', 'Mask', 'ReplaceMask']:
            if field in patch and isinstance(patch[field], list):
                # Convert list of integers to bytes
                patch[field] = bytes(patch[field])

# Fix missing ExecutablePath in kexts
if 'Kernel' in plist_data and 'Add' in plist_data['Kernel']:
    for kext in plist_data['Kernel']['Add']:
        if 'ExecutablePath' not in kext:
            kext['ExecutablePath'] = ''

# Save the fixed plist
with open(config_file, 'wb') as f:
    plistlib.dump(plist_data, f)
"""
    
    try:
        subprocess.run([sys.executable, '-c', python_fix_script], check=True, capture_output=True, text=True)
        log("✓ Binary data format conversion completed")
    except subprocess.CalledProcessError as e:
        warn(f"Python data conversion failed: {e.stderr}")

def main():
    parser = argparse.ArgumentParser(
        description='Apply OpenCore configuration changeset',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("changeset", help="Changeset name (without .yaml extension)")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying them")
    parser.add_argument("--amd-cores", type=int, help="AMD CPU core count for patches (default: 16)")
    
    args = parser.parse_args()
    
    # Construct the changeset path from the name
    changeset_path = ROOT / "config" / "changesets" / f"{args.changeset}.yaml"
    validate_file_exists(changeset_path, "Changeset file")
    validate_file_exists(TEMPLATE_PLIST, "OpenCore template")
    validate_file_exists(PATCHER, "Plist patcher script")
    
    # Load changeset
    log(f"Loading changeset: {changeset_path}")
    try:
        with open(changeset_path, 'r') as f:
            changeset_data = yaml.safe_load(f)
    except Exception as e:
        error(f"Failed to load changeset: {e}")
        return 1
    
    # Check if AMD Vanilla patches are needed
    amd_enabled = False
    if 'kernel_patches' in changeset_data:
        # Check if any kernel patch mentions AMD
        for patch in changeset_data['kernel_patches']:
            comment = patch.get('Comment', '').lower()
            if 'amd' in comment or 'authenticamd' in comment or 'genuineintel' in comment:
                amd_enabled = True
                break
    
    if amd_enabled:
        log("AMD Vanilla patches detected in changeset")
        # Apply AMD patches using the library function
        core_count = args.amd_cores or 16
        changeset_data = apply_amd_vanilla_patches_to_data(changeset_data, core_count)
        log("AMD Vanilla patches applied to changeset")
    else:
        log("No AMD patches detected in changeset")
    
    # Convert changeset to patch operations
    log("Converting changeset to patch operations")
    operations = changeset_to_operations(changeset_data)
    
    # Convert operations to JSON
    try:
        operations_json = json.dumps(operations, cls=CustomJSONEncoder, indent=2)
    except Exception as e:
        error(f"Failed to serialize operations: {e}")
        return 1
    
    if args.dry_run:
        log("DRY RUN MODE - Changes will not be applied")
        print("Operations that would be applied:")
        print(operations_json)
        return 0
    
    # Debug: Show operations data size
    log(f"Operations data size: {len(operations_json)} characters")
    
    # Ensure output directory exists
    EFI.mkdir(parents=True, exist_ok=True)
    
    # Apply changeset using patcher
    log("Applying changeset to OpenCore configuration")
    try:
        # First, copy template to target location
        import shutil
        target_config = EFI / "config.plist"
        shutil.copy2(str(TEMPLATE_PLIST), str(target_config))
        log(f"Copied template from {TEMPLATE_PLIST} to {target_config}")
        
        # Apply operations via patch-plist.py
        cmd = [
            sys.executable, str(PATCHER),
            str(target_config),  # The plist file to patch
            operations_json      # The JSON operations
        ]
        
        result = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
        log("✓ Changeset applied successfully")
        
        if result.stdout:
            log(f"Patcher output: {result.stdout}")
        
        # Post-process the config to fix data format issues
        log("Post-processing config to fix binary data formats...")
        post_process_config(target_config)
        
    except subprocess.CalledProcessError as e:
        error(f"Patcher failed with exit code {e.returncode}")
        if e.stderr:
            error(f"Error output: {e.stderr}")
        return 1
    except Exception as e:
        error(f"Failed to run patcher: {e}")
        return 1
    
    log(f"Successfully applied changeset to {EFI / 'config.plist'}")
    
    # Validate the configuration after applying
    log("Validating applied configuration...")
    validate_script = ROOT / "scripts" / "validate-config.py"
    if validate_script.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(validate_script)],
                cwd=ROOT,
                capture_output=True,
                text=True
            )
            
            if result.returncode == 0:
                log("✓ Configuration validation passed")
            else:
                error("✗ Configuration validation failed")
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr)
                error("Changeset was applied but configuration is invalid!")
                return 1
                
        except Exception as e:
            warn(f"Could not run validation: {e}")
            warn("Changeset applied but validation could not be performed")
    else:
        warn("Validation script not found, skipping validation")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
