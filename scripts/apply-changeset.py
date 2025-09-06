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
    
    # Handle kexts - replace entire Kernel.Add list
    if 'kexts' in changeset_data:
        kext_entries = []
        for kext in changeset_data['kexts']:
            # Set ExecutablePath - empty string if no exec, otherwise Contents/MacOS/exec
            exec_path = ""
            if kext.get('exec') and kext['exec'].strip():
                exec_path = f"Contents/MacOS/{kext['exec']}"
            
            kext_entry = {
                "Arch": "Any",
                "BundlePath": kext['bundle'],
                "Comment": "",
                "Enabled": True,
                "ExecutablePath": exec_path,
                "MaxKernel": "",
                "MinKernel": "",
                "PlistPath": "Contents/Info.plist"
            }
            kext_entries.append(kext_entry)
        
        operations.append({
            "op": "set",
            "path": ["Kernel", "Add"],
            "value": kext_entries
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
            # First, remove any existing entry with the same Path
            operations.append({
                "op": "remove",
                "path": ["ACPI", "Add"],
                "key": "Path",
                "value": acpi_file
            })
            
            # Then append the new entry
            acpi_entry = {
                "Path": acpi_file,
                "Enabled": True,
                "Comment": f"Added by changeset"
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
    
    # Handle tools - remove existing then append to Misc.Tools
    if 'tools' in changeset_data:
        for tool in changeset_data['tools']:
            # First remove any existing tool with the same name
            operations.append({
                "op": "remove",
                "path": ["Misc", "Tools"],
                "key": "Name",
                "value": tool['Name']
            })
            
            # Then append the new tool entry
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
    
    # Handle device properties - set to replace template samples with changeset properties
    if 'device_properties' in changeset_data:
        operations.append({
            "op": "set",
            "path": ["DeviceProperties", "Add"],
            "value": changeset_data['device_properties']
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
    
    # Handle timeout setting - set Misc.Boot.Timeout
    if 'timeout' in changeset_data:
        operations.append({
            "op": "set",
            "path": ["Misc", "Boot", "Timeout"],
            "value": changeset_data['timeout']
        })
    
    # Handle misc_debug settings - set Misc.Debug options
    if 'misc_debug' in changeset_data:
        debug_settings = changeset_data['misc_debug']
        for setting, value in debug_settings.items():
            operations.append({
                "op": "set",
                "path": ["Misc", "Debug", setting],
                "value": value
            })
    
    return operations

def post_process_config(config_path):
    """Fix binary data formats and remove warnings"""
    import subprocess
    import plistlib
    from datetime import datetime
    
    # Load the config
    with open(config_path, 'rb') as f:
        config = plistlib.load(f)
    
    # Convert kernel patch arrays to binary data format
    if 'Kernel' in config and 'Patch' in config['Kernel']:
        for patch in config['Kernel']['Patch']:
            for field in ['Find', 'Replace', 'Mask', 'ReplaceMask']:
                if field in patch and isinstance(patch[field], list):
                    # Convert list of integers to bytes then base64
                    bytes_data = bytes(patch[field])
                    patch[field] = bytes_data
    
    # Convert DeviceProperties base64 strings to binary data
    if 'DeviceProperties' in config and 'Add' in config['DeviceProperties']:
        import base64
        for device_path, properties in config['DeviceProperties']['Add'].items():
            for prop_name, prop_value in properties.items():
                if isinstance(prop_value, str):
                    try:
                        # Convert base64 string to binary data
                        properties[prop_name] = base64.b64decode(prop_value)
                    except:
                        # If it's not valid base64, leave it as string
                        pass
    
    # Remove warning keys
    warning_keys = [key for key in config.keys() if key.startswith('#WARNING')]
    for key in warning_keys:
        config.pop(key, None)
    
    # Remove warning keys from ACPI section
    if 'ACPI' in config:
        acpi_warning_keys = [key for key in config['ACPI'].keys() if key.startswith('#WARNING')]
        for key in acpi_warning_keys:
            config['ACPI'].pop(key, None)
    
    # Remove warning keys from DeviceProperties section
    if 'DeviceProperties' in config:
        device_warning_keys = [key for key in config['DeviceProperties'].keys() if key.startswith('#WARNING')]
        for key in device_warning_keys:
            config['DeviceProperties'].pop(key, None)
    
    # Clear sample ACPI entries - keep only enabled ones or ones added by changeset  
    if 'ACPI' in config and 'Add' in config['ACPI']:
        # Remove all sample/disabled entries to prevent conflicts with changeset
        # Keep only entries that are explicitly enabled (True)
        filtered_entries = []
        for entry in config['ACPI']['Add']:
            # Keep entries that are explicitly enabled (not just default True)
            if entry.get('Enabled') is True:
                filtered_entries.append(entry)
                
        config['ACPI']['Add'] = filtered_entries
    
    # Clear sample Kernel entries - keep only enabled ones from changeset
    if 'Kernel' in config and 'Add' in config['Kernel']:
        filtered_entries = []
        for entry in config['Kernel']['Add']:
            # Only keep entries that are explicitly enabled (True), not default enabled
            if entry.get('Enabled') is True:
                # Ensure ExecutablePath exists, add empty string if missing
                if 'ExecutablePath' not in entry:
                    entry['ExecutablePath'] = ""
                filtered_entries.append(entry)
                
        config['Kernel']['Add'] = filtered_entries
    
    # Add generation timestamp
    current_time = datetime.now()
    config['#Generated'] = current_time.strftime('%Y-%m-%d %H:%M:%S')
    
    # Save the updated config
    with open(config_path, 'wb') as f:
        plistlib.dump(config, f)

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
