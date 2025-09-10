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
    validate_file_exists, validate_changeset_exists
)
from lib.changeset import apply_amd_vanilla_patches_to_data, get_amd_vanilla_patch_info

# Project-specific paths
EFI = ROOT / "out" / "build" / "efi" / "EFI" / "OC"
TEMPLATE_PLIST = ROOT / "assets" / "config.plist.TEMPLATE"
PATCHER = ROOT / "scripts" / "patch-plist.py"

def copy_acpi_files(acpi_files):
    """Copy ACPI .aml files from OpenCore samples or assets directory to the ACPI directory"""
    if not acpi_files:
        return
        
    # Find OpenCore ACPI samples directory
    opencore_path = ROOT / "out" / "opencore"
    acpi_samples_dir = opencore_path / "Docs" / "AcpiSamples" / "Binaries"
    
    # Ensure ACPI directory exists
    acpi_target_dir = EFI / "ACPI"
    acpi_target_dir.mkdir(parents=True, exist_ok=True)
    
    copied_count = 0
    for acpi_file in acpi_files:
        # Check multiple locations for ACPI files, in order of preference:
        # 1. OpenCore samples (first priority)
        # 2. Assets directory (second priority)
        source_locations = [
            acpi_samples_dir / acpi_file,
            ROOT / "assets" / acpi_file
        ]
        
        source_file = None
        for location in source_locations:
            if location.exists():
                source_file = location
                break
        
        target_file = acpi_target_dir / acpi_file
        
        if source_file:
            import shutil
            shutil.copy2(source_file, target_file)
            copied_count += 1
            log(f"✓ Copied ACPI file: {acpi_file} (from {source_file.parent.name})")
        else:
            warn(f"ACPI file not found: {acpi_file} (searched in OpenCore samples and assets)")
    
    if copied_count > 0:
        log(f"✓ Copied {copied_count} ACPI file(s)")

def validate_changeset_structure(changeset_data):
    """Validate changeset structure and check for conflicts"""
    
    # Check for duplicate boot-args definitions
    has_boot_args_top_level = 'boot_args' in changeset_data or 'BootArgs' in changeset_data
    has_boot_args_nvram = False
    
    if 'NVRAM' in changeset_data:
        nvram_add = changeset_data['NVRAM'].get('Add') or changeset_data['NVRAM'].get('add')
        if nvram_add:
            for guid, values in nvram_add.items():
                if isinstance(values, dict) and 'boot-args' in values:
                    has_boot_args_nvram = True
                    break
    
    if has_boot_args_top_level and has_boot_args_nvram:
        error("Changeset contains duplicate boot-args definitions!")
        error("Found both top-level 'BootArgs'/'boot_args' and 'boot-args' in NVRAM section.")
        error("Please use only one format - preferably in NVRAM section.")
        sys.exit(1)
    
    if has_boot_args_top_level:
        warn("Top-level 'boot_args' is deprecated. Consider moving to NVRAM section as 'boot-args'.")

def apply_platform_info_to_nvram(changeset_data):
    """Copy PlatformInfo.Generic to NVRAM for Apple ID if enabled"""
    
    # Check if the feature is enabled (default: true)
    copy_to_nvram = changeset_data.get('PlatformInfoGenericCopyToNvramForAppleId', True)
    
    if not copy_to_nvram:
        return changeset_data
    
    # Check if PlatformInfo.Generic exists
    if not ('PlatformInfo' in changeset_data and 'Generic' in changeset_data['PlatformInfo']):
        return changeset_data
    
    log("Copying PlatformInfo.Generic to NVRAM for Apple ID...")
    
    platform_info = changeset_data['PlatformInfo']['Generic']
    
    # Initialize NVRAM structure if it doesn't exist
    if 'NVRAM' not in changeset_data:
        changeset_data['NVRAM'] = {}
    if 'Add' not in changeset_data['NVRAM']:
        changeset_data['NVRAM']['Add'] = {}
    
    # Apple GUID for identity keys
    apple_guid = '4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14'
    
    if apple_guid not in changeset_data['NVRAM']['Add']:
        changeset_data['NVRAM']['Add'][apple_guid] = {}
    
    # Copy relevant fields to NVRAM
    apple_nvram = changeset_data['NVRAM']['Add'][apple_guid]
    
    nvram_fields = ['SystemProductName', 'SystemSerialNumber', 'MLB', 'SystemUUID', 'ROM']
    for field in nvram_fields:
        if field in platform_info:
            if field == 'ROM':
                # Convert ROM hex string to bytes for NVRAM
                rom_value = platform_info[field]
                if isinstance(rom_value, str):
                    # Convert hex string to bytes
                    try:
                        hex_str = rom_value.replace(' ', '')
                        apple_nvram[field] = bytes.fromhex(hex_str)
                        log(f"  Copied {field} to NVRAM (converted hex to bytes)")
                    except ValueError:
                        apple_nvram[field] = rom_value
                        log(f"  Copied {field} to NVRAM (kept as string due to conversion error)")
                else:
                    apple_nvram[field] = rom_value
                    log(f"  Copied {field} to NVRAM")
            else:
                apple_nvram[field] = platform_info[field]
                log(f"  Copied {field} to NVRAM")
    
    return changeset_data

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
    kexts = changeset_data.get('Kexts', changeset_data.get('kexts'))
    if kexts:
        kext_entries = []
        for kext in kexts:
            # Set ExecutablePath - empty string if no exec, otherwise Contents/MacOS/exec
            exec_path = ""
            if kext.get('exec') and kext['exec'].strip():
                exec_path = f"Contents/MacOS/{kext['exec']}"
            
            kext_entry = {
                "Arch": "Any",
                "BundlePath": kext['bundle'],
                "Comment": kext['bundle'],  # Use bundle path as comment
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
    if 'BooterQuirks' in changeset_data:
        operations.append({
            "op": "merge",
            "path": ["Booter", "Quirks"],
            "entries": changeset_data['BooterQuirks']
        })
    
    # Handle kernel quirks - merge into Kernel.Quirks
    if 'KernelQuirks' in changeset_data:
        quirks = changeset_data['KernelQuirks'].copy()
        
        # Check for DummyPowerManagement in quirks and move it to emulate
        if 'DummyPowerManagement' in quirks:
            print("ERROR: DummyPowerManagement found in KernelQuirks but should be in Kernel.Emulate section!")
            print("Please move DummyPowerManagement from KernelQuirks to KernelEmulate in your changeset.")
            sys.exit(1)
        
        if quirks:  # Only add operation if there are remaining quirks
            operations.append({
                "op": "merge",
                "path": ["Kernel", "Quirks"],
                "entries": quirks
            })
    
    # Handle kernel emulate settings - merge into Kernel.Emulate
    kernel_emulate = changeset_data.get('KernelEmulate', changeset_data.get('kernel_emulate'))
    if kernel_emulate:
        operations.append({
            "op": "merge",
            "path": ["Kernel", "Emulate"],
            "entries": kernel_emulate
        })
    
    # Handle kernel patches - set Kernel.Patch
    kernel_patches = changeset_data.get('KernelPatches', changeset_data.get('kernel_patches'))
    if kernel_patches:
        # Ensure all binary fields are properly formatted as bytes
        patches = ensure_bytes_for_kernel_patches(kernel_patches)
        operations.append({
            "op": "set",
            "path": ["Kernel", "Patch"],
            "value": patches
        })
    
    # Handle boot-args - can be defined as top-level BootArgs/boot_args OR in NVRAM section
    # Check for both formats and ensure only one is used
    top_level_boot_args = changeset_data.get('BootArgs', changeset_data.get('boot_args'))
    nvram_boot_args = None
    
    # Check if boot-args exists in NVRAM section (handle both Add and add)
    if 'NVRAM' in changeset_data:
        nvram_add = changeset_data['NVRAM'].get('Add') or changeset_data['NVRAM'].get('add')
        if nvram_add:
            for guid, variables in nvram_add.items():
                if isinstance(variables, dict) and 'boot-args' in variables:
                    nvram_boot_args = variables['boot-args']
                    break
    
    # Validate that only one format is used
    if top_level_boot_args and nvram_boot_args:
        error("Changeset contains duplicate boot-args definitions!")
        error("Found both top-level 'BootArgs'/'boot_args' and 'boot-args' in NVRAM section.")
        error("Please use only one format - preferably in NVRAM section.")
        sys.exit(1)
    
    # Process boot-args (convert top-level to NVRAM format if needed)
    final_boot_args = top_level_boot_args or nvram_boot_args
    if final_boot_args:
        if top_level_boot_args:
            log("Converting top-level BootArgs to NVRAM boot-args format")
        
        operations.append({
            "op": "set",
            "path": ["NVRAM", "Add", "7C436110-AB2A-4BBB-A880-FE41995C9F82", "boot-args"],
            "value": final_boot_args
        })

    # Handle CSR config - set NVRAM entry
    csr_config = changeset_data.get('CsrActiveConfig', changeset_data.get('csr_active_config'))
    if csr_config:
        # Convert hex string to bytes
        if isinstance(csr_config, str):
            # Remove any spaces and convert pairs of hex chars to bytes
            csr_clean = csr_config.replace(' ', '')
            csr_bytes = [int(csr_clean[i:i+2], 16) for i in range(0, len(csr_clean), 2)]
        else:
            csr_bytes = csr_config
        operations.append({
            "op": "set", 
            "path": ["NVRAM", "Add", "7C436110-AB2A-4BBB-A880-FE41995C9F82", "csr-active-config"],
            "value": csr_bytes
        })
    
    # Handle PlatformInfo - merge into PlatformInfo.Generic
    if 'PlatformInfo' in changeset_data and 'Generic' in changeset_data['PlatformInfo']:
        # Convert data values (e.g., hex ROM to bytes)
        converted_generic = convert_data_values(changeset_data['PlatformInfo']['Generic'])
        operations.append({
            "op": "merge",
            "path": ["PlatformInfo", "Generic"],
            "entries": converted_generic
        })
    
    # Handle ACPI add - append to ACPI.Add
    if 'AcpiAdd' in changeset_data:
        for acpi_file in changeset_data['AcpiAdd']:
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
                "Comment": acpi_file  # Use filename as comment
            }
            operations.append({
                "op": "append",
                "path": ["ACPI", "Add"],
                "entry": acpi_entry,
                "key": "Path"
            })
    
    # Handle ACPI quirks - merge into ACPI.Quirks
    acpi_quirks = changeset_data.get('AcpiQuirks', changeset_data.get('acpi_quirks'))
    if acpi_quirks:
        operations.append({
            "op": "merge",
            "path": ["ACPI", "Quirks"],
            "entries": acpi_quirks
        })
    
    # Handle UEFI drivers - append to UEFI.Drivers
    if 'UefiDrivers' in changeset_data:
        for driver in changeset_data['UefiDrivers']:
            driver_entry = {
                "Path": driver['path'],
                "Enabled": driver.get('enabled', True),
                "LoadEarly": driver.get('LoadEarly', False)
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
    tools = changeset_data.get('MiscTools', changeset_data.get('tools'))
    if tools:
        for tool in tools:
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
                "Arguments": tool.get('Arguments', ''),
                "Auxiliary": tool.get('Auxiliary', False),
                "Comment": tool.get('Comment', ''),
                "Flavour": tool.get('Flavour', 'Auto'),
                "FullNvramAccess": tool.get('FullNvramAccess', False),
                "RealPath": tool.get('RealPath', False),
                "TextMode": tool.get('TextMode', False)
            }
            operations.append({
                "op": "append",
                "path": ["Misc", "Tools"],
                "entry": tool_entry,
                "key": "Name"
            })
    
    # Handle device properties - set to replace template samples with changeset properties
    device_props = changeset_data.get('DeviceProperties', changeset_data.get('device_properties'))
    if device_props:
        operations.append({
            "op": "set",
            "path": ["DeviceProperties", "Add"],
            "value": device_props
        })
    
    # Handle security settings
    secureboot_model = changeset_data.get('SecureBootModel', changeset_data.get('secureboot_model'))
    if secureboot_model:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "SecureBootModel"],
            "value": secureboot_model
        })
    
    vault = changeset_data.get('Vault', changeset_data.get('vault'))
    if vault:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "Vault"],
            "value": vault
        })
    
    scan_policy = changeset_data.get('ScanPolicy', changeset_data.get('scan_policy'))
    if scan_policy:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "ScanPolicy"],
            "value": scan_policy
        })
    
    # Handle misc_debug settings - set Misc.Debug options
    misc_debug = changeset_data.get('MiscDebug', changeset_data.get('misc_debug'))
    if misc_debug:
        for setting, value in misc_debug.items():
            operations.append({
                "op": "set",
                "path": ["Misc", "Debug", setting],
                "value": value
            })
    
    # Handle misc_serial settings - set Misc.Serial options
    misc_serial = changeset_data.get('MiscSerial', changeset_data.get('misc_serial'))
    if misc_serial:
        for setting, value in misc_serial.items():
            operations.append({
                "op": "set",
                "path": ["Misc", "Serial", setting],
                "value": value
            })
    
    # Handle NVRAM settings
    if 'NVRAM' in changeset_data:
        nvram_data = changeset_data['NVRAM']
        
        # Handle NVRAM Add section
        if 'Add' in nvram_data:
            for guid, variables in nvram_data['Add'].items():
                for var_name, var_value in variables.items():
                    # Skip boot-args as it's handled separately above
                    if var_name == 'boot-args':
                        continue
                    operations.append({
                        "op": "set",
                        "path": ["NVRAM", "Add", guid, var_name],
                        "value": var_value
                    })
        
        # Handle NVRAM Delete section
        if 'Delete' in nvram_data:
            for guid, variables in nvram_data['Delete'].items():
                if isinstance(variables, list):
                    # Set the delete array for this GUID
                    operations.append({
                        "op": "set",
                        "path": ["NVRAM", "Delete", guid],
                        "value": variables
                    })
        
        # Handle WriteFlash setting (case-insensitive)
        writeflash_value = None
        for key in nvram_data.keys():
            if key.lower() == 'writeflash':
                writeflash_value = nvram_data[key]
                break
        
        if writeflash_value is not None:
            operations.append({
                "op": "set", 
                "path": ["NVRAM", "WriteFlash"],
                "value": writeflash_value
            })
    
    # Handle nested misc_boot settings - set Misc.Boot options
    misc_boot = changeset_data.get('MiscBoot', changeset_data.get('misc_boot'))
    if misc_boot:
        # Map snake_case to correct OpenCore PascalCase
        boot_key_mapping = {
            'timeout': 'Timeout',
            'picker_mode': 'PickerMode',
            'poll_apple_hot_keys': 'PollAppleHotKeys',
            'show_picker': 'ShowPicker',
            'hide_auxiliary': 'HideAuxiliary',
            'picker_attributes': 'PickerAttributes',
            'picker_audio_assist': 'PickerAudioAssist',
            'picker_variant': 'PickerVariant',
            'console_attributes': 'ConsoleAttributes',
            'takeoff_delay': 'TakeoffDelay',
            'hibernate_mode': 'HibernateMode',
            'hibernate_skips_picker': 'HibernateSkipsPicker',
            'instance_identifier': 'InstanceIdentifier',
            'launcher_option': 'LauncherOption',
            'launcher_path': 'LauncherPath'
        }
        
        for setting, value in misc_boot.items():
            plist_key = boot_key_mapping.get(setting, setting)
            operations.append({
                "op": "set",
                "path": ["Misc", "Boot", plist_key],
                "value": value
            })
    
    # Handle BlessOverride setting - set Misc.BlessOverride (only if not empty)
    misc_bless_override = changeset_data.get('MiscBlessOverride', changeset_data.get('misc_bless_override'))
    if misc_bless_override:
        operations.append({
            "op": "set",
            "path": ["Misc", "BlessOverride"],
            "value": misc_bless_override
        })
    
    # Handle nested misc_security settings - set Misc.Security options
    misc_security = changeset_data.get('MiscSecurity', changeset_data.get('misc_security'))
    if misc_security:
        # Map snake_case to correct OpenCore PascalCase
        security_key_mapping = {
            'secureboot_model': 'SecureBootModel',
            'vault': 'Vault',
            'scan_policy': 'ScanPolicy',
            'allow_set_default': 'AllowSetDefault',
            'expose_sensitive_data': 'ExposeSensitiveData',
            'auth_restart': 'AuthRestart',
            'blacklist_apple_update': 'BlacklistAppleUpdate',
            'dmg_loading': 'DmgLoading',
            'enable_password': 'EnablePassword',
            'halt_level': 'HaltLevel'
        }
        
        for setting, value in misc_security.items():
            plist_key = security_key_mapping.get(setting, setting)
            operations.append({
                "op": "set",
                "path": ["Misc", "Security", plist_key],
                "value": value
            })
    
    # Handle additional Security settings (legacy support)
    allow_set_default = changeset_data.get('AllowSetDefault', changeset_data.get('allow_set_default'))
    if allow_set_default is not None:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "AllowSetDefault"],
            "value": allow_set_default
        })
    
    expose_sensitive_data = changeset_data.get('ExposeSensitiveData', changeset_data.get('expose_sensitive_data'))
    if expose_sensitive_data is not None:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "ExposeSensitiveData"],
            "value": expose_sensitive_data
        })
    
    auth_restart = changeset_data.get('AuthRestart', changeset_data.get('auth_restart'))
    if auth_restart is not None:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "AuthRestart"],
            "value": auth_restart
        })
    
    blacklist_apple_update = changeset_data.get('BlacklistAppleUpdate', changeset_data.get('blacklist_apple_update'))
    if blacklist_apple_update is not None:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "BlacklistAppleUpdate"],
            "value": blacklist_apple_update
        })
    
    dmg_loading = changeset_data.get('DmgLoading', changeset_data.get('dmg_loading'))
    if dmg_loading is not None:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "DmgLoading"],
            "value": dmg_loading
        })
    
    enable_password = changeset_data.get('EnablePassword', changeset_data.get('enable_password'))
    if enable_password is not None:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "EnablePassword"],
            "value": enable_password
        })
    
    halt_level = changeset_data.get('HaltLevel', changeset_data.get('halt_level'))
    if halt_level is not None:
        operations.append({
            "op": "set",
            "path": ["Misc", "Security", "HaltLevel"],
            "value": halt_level
        })
    
    # Handle Misc Tools (TitleCase format)
    if 'MiscTools' in changeset_data:
        tools_list = changeset_data['MiscTools']
        
        # Only set Tools if there are actual tools to add
        if tools_list:
            tools_array = []
            
            # Add each tool individually to ensure proper structure
            for tool in tools_list:
                tool_entry = {
                    "Name": tool['Name'],
                    "Path": tool['Path'], 
                    "Enabled": tool.get('Enabled', True),
                    "Arguments": tool.get('Arguments', ''),
                    "Auxiliary": tool.get('Auxiliary', False),
                    "Comment": tool.get('Comment', ''),
                    "Flavour": tool.get('Flavour', 'Auto'),
                    "FullNvramAccess": tool.get('FullNvramAccess', False),
                    "RealPath": tool.get('RealPath', False),
                    "TextMode": tool.get('TextMode', False)
                }
                tools_array.append(tool_entry)
            
            # Set the tools array only if there are tools
            operations.append({
                "op": "set",
                "path": ["Misc", "Tools"],
                "value": tools_array
            })
        # If tools_list is empty, don't set anything - let template handle it
    
    # Handle Misc Entries (TitleCase format - only if there are actual entries)
    if 'MiscEntries' in changeset_data and changeset_data['MiscEntries']:
        # Replace the entire Entries array only if there are actual entries
        operations.append({
            "op": "set",
            "path": ["Misc", "Entries"],
            "value": changeset_data['MiscEntries']
        })
    # If empty entries, don't set anything - let template default handle it
    
    # Handle UEFI Output settings
    uefi_output = changeset_data.get('UefiOutput', changeset_data.get('uefi_output'))
    if uefi_output:
        for setting, value in uefi_output.items():
            operations.append({
                "op": "set",
                "path": ["UEFI", "Output", setting],
                "value": value
            })
    
    # Handle UEFI APFS settings
    uefi_apfs = changeset_data.get('UefiApfs', changeset_data.get('uefi_apfs'))
    if uefi_apfs:
        for setting, value in uefi_apfs.items():
            operations.append({
                "op": "set",
                "path": ["UEFI", "APFS", setting],
                "value": value
            })
    
    # Handle UEFI Quirks
    uefi_quirks = changeset_data.get('UefiQuirks', changeset_data.get('uefi_quirks'))
    if uefi_quirks:
        for setting, value in uefi_quirks.items():
            operations.append({
                "op": "set",
                "path": ["UEFI", "Quirks", setting],
                "value": value
            })
    
    # Handle ConnectDrivers
    connect_drivers = changeset_data.get('ConnectDrivers', changeset_data.get('connect_drivers'))
    if connect_drivers is not None:
        operations.append({
            "op": "set",
            "path": ["UEFI", "ConnectDrivers"],
            "value": connect_drivers
        })
    
    # Handle Protocol Overrides
    protocol_overrides = changeset_data.get('ProtocolOverrides', changeset_data.get('protocol_overrides'))
    if protocol_overrides:
        for setting, value in protocol_overrides.items():
            operations.append({
                "op": "set",
                "path": ["UEFI", "ProtocolOverrides", setting],
                "value": value
            })
    
    # Handle Reserved Memory
    reserved_memory = changeset_data.get('ReservedMemory', changeset_data.get('reserved_memory'))
    if reserved_memory:
        operations.append({
            "op": "set",
            "path": ["UEFI", "ReservedMemory"],
            "value": reserved_memory
        })

    return operations

def post_process_config(config_path):
    """Fix binary data formats and remove warnings"""
    import subprocess
    import plistlib
    import re
    from datetime import datetime
    
    def format_short_data_tags(xml_content, max_length=20):
        """Format short base64 data tags to be on a single line."""
        # Pattern 1: Match <data> tags with content spread across lines
        pattern1 = r'<data>\s*\n\s*([A-Za-z0-9+/=]+)\s*\n\s*</data>'
        
        # Pattern 2: Match empty <data> tags spread across lines
        pattern2 = r'<data>\s*\n\s*</data>'
        
        def replace_data_tag(match):
            base64_content = match.group(1).strip()
            
            # Only format short base64 strings as single line
            if len(base64_content) <= max_length:
                return f'<data>{base64_content}</data>'
            else:
                # Keep longer data on multiple lines with proper indentation
                return match.group(0)
        
        # First handle non-empty data tags
        formatted_content = re.sub(pattern1, replace_data_tag, xml_content)
        
        # Then handle empty data tags
        formatted_content = re.sub(pattern2, '<data></data>', formatted_content)
        
        return formatted_content
    
    def convert_tabs_to_spaces(xml_content, spaces=2):
        """Convert tabs to spaces in XML content."""
        return xml_content.replace('\t', ' ' * spaces)
    
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
                    # Only convert to binary if it looks like base64 and is a property that should be binary
                    # Properties like layout-id, device-id, etc. are typically base64
                    # Properties like hda-gfx, model, AAPL,ig-platform-id are often strings
                    binary_properties = [
                        'layout-id', 'device-id', 'vendor-id', 'subsystem-id', 
                        'subsystem-vendor-id', 'built-in', 'class-code', 'compatible',
                        'reg', 'acpi-path', 'acpi-device', 'AAPL,slot-name',
                        'pci-aspm-default', 'AAPL,boot-display'
                    ]
                    if prop_name in binary_properties:
                        try:
                            # Convert base64 string to binary data
                            properties[prop_name] = base64.b64decode(prop_value)
                        except:
                            # If it's not valid base64, leave it as string
                            pass
                    # Leave other properties as strings (hda-gfx, model, etc.)
    
    # Convert NVRAM base64 strings to binary data
    if 'NVRAM' in config and 'Add' in config['NVRAM']:
        for guid, variables in config['NVRAM']['Add'].items():
            for var_name, var_value in variables.items():
                if isinstance(var_value, str):
                    # Special handling for known binary fields
                    if var_name in ['DefaultBackgroundColor', 'csr-active-config', 'prev-lang:kbd']:
                        try:
                            # Convert base64 string to binary data
                            variables[var_name] = base64.b64decode(var_value)
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
    
    # Format short data tags to be on single lines
    with open(config_path, 'r') as f:
        xml_content = f.read()

    formatted_content = format_short_data_tags(xml_content)
    formatted_content = convert_tabs_to_spaces(formatted_content, spaces=2)

    with open(config_path, 'w') as f:
        f.write(formatted_content)

def main():
    parser = argparse.ArgumentParser(
        description='Apply OpenCore configuration changeset',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("changeset", help="Changeset name (without .yaml extension)")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying them")
    parser.add_argument("--amd-cores", type=int, help="AMD CPU core count for patches (default: 16)")
    
    args = parser.parse_args()
    
    # Validate changeset exists
    changeset_path = validate_changeset_exists(args.changeset)
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
    
    # Validate changeset structure
    validate_changeset_structure(changeset_data)
    
    # Apply platform_info to NVRAM if enabled
    changeset_data = apply_platform_info_to_nvram(changeset_data)
    
    # Copy ACPI files if specified in changeset
    acpi_add = changeset_data.get('AcpiAdd', changeset_data.get('acpi_add'))
    if acpi_add:
        copy_acpi_files(acpi_add)
    
    # Handle AMD Vanilla patches flag
    amd_enabled = False
    amd_vanilla_patches = changeset_data.get('AmdVanillaPatches', changeset_data.get('amd_vanilla_patches', False))
    if amd_vanilla_patches:
        amd_enabled = True
        log("AMD Vanilla patches enabled in changeset")
        # Load and modify AMD patches
        from lib.changeset import load_amd_vanilla_patches, modify_amd_core_count_patches
        
        amd_patches = load_amd_vanilla_patches()
        if amd_patches:
            core_count = args.amd_cores or 16
            modified_amd_patches = modify_amd_core_count_patches(amd_patches, core_count)
            
            # Merge with any existing kernel patches
            existing_patches = changeset_data.get('KernelPatches', changeset_data.get('kernel_patches', []))
            if existing_patches:
                log(f"Merging {len(modified_amd_patches)} AMD patches with {len(existing_patches)} existing kernel patches")
                changeset_data['KernelPatches'] = existing_patches + modified_amd_patches
            else:
                log(f"Adding {len(modified_amd_patches)} AMD patches to changeset")
                changeset_data['KernelPatches'] = modified_amd_patches
        else:
            warn("AMD Vanilla patches requested but could not be loaded")
    
    # Legacy detection for backwards compatibility
    elif 'kernel_patches' in changeset_data:
        # Check if any kernel patch mentions AMD
        for patch in changeset_data['kernel_patches']:
            comment = patch.get('Comment', '').lower()
            if 'amd' in comment or 'authenticamd' in comment or 'algrey' in comment:
                amd_enabled = True
                log("AMD patches detected in kernel_patches (legacy format)")
                break
    
    if not amd_enabled:
        log("No AMD patches detected or enabled in changeset")
    
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
