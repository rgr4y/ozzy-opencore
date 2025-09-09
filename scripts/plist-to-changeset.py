#!/usr/bin/env python3.11
"""
Convert OpenCore config.plist to changeset format.

This script analyzes a working config.plist and converts it into a changeset
that can be used with the ozzy build system.
"""

import sys
import argparse
import plistlib
import yaml
import base64
from pathlib import Path
from typing import Dict, Any, List, Union

# Import our common libraries
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import ROOT, log, warn, error, info

def convert_bytes_to_strings(obj: Any) -> Any:
    """
    Recursively convert bytes objects to appropriate formats to avoid PyYAML's !!binary formatting.
    - Empty bytes: Remove the field entirely (return None for removal)
    - Short single-line base64 strings (4+ bytes): Convert to plain strings
    - Very short binary data (1-3 bytes): Keep as bytes for !!binary format
    """
    if isinstance(obj, bytes):
        if len(obj) == 0:
            return None  # Signal to remove this field
        elif len(obj) >= 4:
            # Convert longer binary data to plain base64 strings
            return base64.b64encode(obj).decode('ascii')
        else:
            # Keep very short binary data as bytes for proper !!binary formatting
            return obj
    elif isinstance(obj, dict):
        result = {}
        for k, v in obj.items():
            converted = convert_bytes_to_strings(v)
            if converted is not None:  # Only include non-None values
                result[k] = converted
        return result
    elif isinstance(obj, list):
        return [convert_bytes_to_strings(item) for item in obj if convert_bytes_to_strings(item) is not None]
    else:
        return obj

def load_plist(plist_path: Path) -> Dict[str, Any]:
    """Load a plist file and return its contents"""
    try:
        with open(plist_path, 'rb') as f:
            return plistlib.load(f)
    except Exception as e:
        error(f"Failed to load plist: {e}")
        return {}

def extract_acpi_add(config: Dict[str, Any]) -> List[str]:
    """Extract ACPI Add entries"""
    acpi_add = []
    if 'ACPI' in config and 'Add' in config['ACPI']:
        for entry in config['ACPI']['Add']:
            if entry.get('Enabled', False) and 'Path' in entry:
                acpi_add.append(entry['Path'])
    return acpi_add

def extract_kexts(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract Kernel.Add (kexts) entries"""
    kexts = []
    if 'Kernel' in config and 'Add' in config['Kernel']:
        for entry in config['Kernel']['Add']:
            if entry.get('Enabled', False):
                kext = {
                    'bundle': entry.get('BundlePath', ''),
                    'exec': entry.get('ExecutablePath', '').replace('Contents/MacOS/', '')
                }
                # Clean up executable path
                if kext['exec'].startswith('Contents/MacOS/'):
                    kext['exec'] = kext['exec'][15:]
                kexts.append(kext)
    return kexts

def extract_booter_quirks(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract Booter.Quirks"""
    if 'Booter' in config and 'Quirks' in config['Booter']:
        return config['Booter']['Quirks']
    return {}

def extract_kernel_quirks(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract Kernel.Quirks"""
    if 'Kernel' in config and 'Quirks' in config['Kernel']:
        return config['Kernel']['Quirks']
    return {}

def extract_kernel_emulate(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract Kernel.Emulate"""
    if 'Kernel' in config and 'Emulate' in config['Kernel']:
        return config['Kernel']['Emulate']
    return {}

def extract_kernel_patches(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract Kernel.Patch entries"""
    patches = []
    if 'Kernel' in config and 'Patch' in config['Kernel']:
        for patch in config['Kernel']['Patch']:
            if patch.get('Enabled', False):
                patches.append(patch)
    return patches

def extract_platform_info(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract PlatformInfo data"""
    platform_info = {}
    if 'PlatformInfo' in config:
        platform_config = config['PlatformInfo']
        if 'Generic' in platform_config:
            generic = platform_config['Generic']
            
            # Handle ROM data conversion to hex format
            rom_data = generic.get('ROM', b'')
            if isinstance(rom_data, bytes) and rom_data:
                # Convert bytes to hex string (uppercase, no separators)
                rom_hex = rom_data.hex().upper()
            else:
                rom_hex = ''
            
            platform_info['generic'] = {
                'SystemProductName': generic.get('SystemProductName', ''),
                'SystemSerialNumber': generic.get('SystemSerialNumber', ''),
                'MLB': generic.get('MLB', ''),
                'SystemUUID': generic.get('SystemUUID', ''),
                'ROM': rom_hex
            }
            log("Extracted PlatformInfo.Generic configuration from source config")
    return platform_info

def extract_nvram(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract NVRAM configuration"""
    nvram = {}
    if 'NVRAM' in config:
        nvram_config = config['NVRAM']
        if 'Add' in nvram_config:
            nvram['add'] = nvram_config['Add']
        if 'Delete' in nvram_config:
            nvram['delete'] = nvram_config['Delete']
        if 'WriteFlash' in nvram_config:
            nvram['WriteFlash'] = nvram_config['WriteFlash']
    return nvram

def extract_boot_args(config: Dict[str, Any]) -> str:
    """Extract boot-args from NVRAM"""
    if ('NVRAM' in config and 
        'Add' in config['NVRAM'] and
        '7C436110-AB2A-4BBB-A880-FE41995C9F82' in config['NVRAM']['Add']):
        nvram_guid = config['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']
        return nvram_guid.get('boot-args', '')
    return ''

def extract_misc_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract various Misc settings"""
    misc = {}
    if 'Misc' in config:
        misc_config = config['Misc']
        
        # Security settings - nested under MiscSecurity
        if 'Security' in misc_config:
            security = misc_config['Security']
            misc['MiscSecurity'] = {
                'SecureBootModel': security.get('SecureBootModel', 'Default'),
                'Vault': security.get('Vault', 'Optional'),
                'ScanPolicy': security.get('ScanPolicy', 0),
                'AllowSetDefault': security.get('AllowSetDefault', True),
                'ExposeSensitiveData': security.get('ExposeSensitiveData', 6),
                'AuthRestart': security.get('AuthRestart', False),
                'BlacklistAppleUpdate': security.get('BlacklistAppleUpdate', True),
                'DmgLoading': security.get('DmgLoading', 'Signed'),
                'EnablePassword': security.get('EnablePassword', False),
                'HaltLevel': security.get('HaltLevel', 2147483648)
            }
        
        # Boot settings - nested under MiscBoot
        if 'Boot' in misc_config:
            boot = misc_config['Boot']
            misc['MiscBoot'] = {
                'Timeout': boot.get('Timeout', 5),
                'PickerMode': boot.get('PickerMode', 'Builtin'),
                'PollAppleHotKeys': boot.get('PollAppleHotKeys', False),
                'ShowPicker': boot.get('ShowPicker', True),
                'HideAuxiliary': boot.get('HideAuxiliary', True),
                'PickerAttributes': boot.get('PickerAttributes', 1),
                'PickerAudioAssist': boot.get('PickerAudioAssist', False),
                'PickerVariant': boot.get('PickerVariant', 'Auto'),
                'ConsoleAttributes': boot.get('ConsoleAttributes', 0),
                'TakeoffDelay': boot.get('TakeoffDelay', 0),
                'HibernateMode': boot.get('HibernateMode', 'None'),
                'HibernateSkipsPicker': boot.get('HibernateSkipsPicker', False),
                'InstanceIdentifier': boot.get('InstanceIdentifier', ''),
                'LauncherOption': boot.get('LauncherOption', 'Disabled'),
                'LauncherPath': boot.get('LauncherPath', 'Default')
            }
        
        # BlessOverride settings
        if 'BlessOverride' in misc_config:
            bless_override = misc_config['BlessOverride']
            # Include BlessOverride even if empty array
            misc['MiscBlessOverride'] = bless_override
        
        # Debug settings
        if 'Debug' in misc_config:
            debug = misc_config['Debug']
            misc['MiscDebug'] = {
                'Target': debug.get('Target', 0),
                'AppleDebug': debug.get('AppleDebug', False),
                'ApplePanic': debug.get('ApplePanic', False),
                'DisableWatchDog': debug.get('DisableWatchDog', False),
                'SysReport': debug.get('SysReport', False),
                'DisplayDelay': debug.get('DisplayDelay', 0),
                'DisplayLevel': debug.get('DisplayLevel', 2147483650),
                'LogModules': debug.get('LogModules', '*')
            }
        
        # Tools settings
        if 'Tools' in misc_config:
            tools = misc_config['Tools']
            misc['MiscTools'] = []
            for tool in tools:
                # Only extract the essential fields to match minimal structure
                misc['MiscTools'].append({
                    'Name': tool.get('Name', ''),
                    'Path': tool.get('Path', ''),
                    'Enabled': tool.get('Enabled', False)
                })
        
        # Entries settings
        if 'Entries' in misc_config:
            entries = misc_config['Entries']
            misc['MiscEntries'] = []
            for entry in entries:
                misc['MiscEntries'].append({
                    'Name': entry.get('Name', ''),
                    'Path': entry.get('Path', ''),
                    'Enabled': entry.get('Enabled', False),
                    'Arguments': entry.get('Arguments', ''),
                    'Auxiliary': entry.get('Auxiliary', False),
                    'Comment': entry.get('Comment', ''),
                    'Flavour': entry.get('Flavour', 'Auto'),
                    'TextMode': entry.get('TextMode', False)
                })
        
        # Serial settings
        if 'Serial' in misc_config:
            serial = misc_config['Serial']
            misc['MiscSerial'] = {
                'Init': serial.get('Init', False),
                'Override': serial.get('Override', False)
            }
    
    return misc

def extract_uefi_drivers(config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract UEFI.Drivers"""
    drivers = []
    if 'UEFI' in config and 'Drivers' in config['UEFI']:
        for driver in config['UEFI']['Drivers']:
            if driver.get('Enabled', False):
                drivers.append({
                    'path': driver.get('Path', ''),
                    'enabled': True,
                    'LoadEarly': driver.get('LoadEarly', False),
                    'arguments': driver.get('Arguments', ''),
                    'comment': driver.get('Comment', f"{driver.get('Path', '')} driver")
                })
    return drivers

def extract_uefi_settings(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract UEFI settings (Output, APFS, Input, Audio, etc.)"""
    uefi = {}
    if 'UEFI' in config:
        uefi_config = config['UEFI']
        
        # Output settings
        if 'Output' in uefi_config:
            output = uefi_config['Output']
            uefi['UefiOutput'] = {
                'Resolution': output.get('Resolution', 'Max'),
                'UIScale': output.get('UIScale', 0),
                'TextRenderer': output.get('TextRenderer', 'BuiltinGraphics'),
                'ConsoleMode': output.get('ConsoleMode', ''),
                'ConsoleFont': output.get('ConsoleFont', ''),
                'ClearScreenOnModeSwitch': output.get('ClearScreenOnModeSwitch', False),
                'DirectGopRendering': output.get('DirectGopRendering', False),
                'ForceResolution': output.get('ForceResolution', False),
                'GopBurstMode': output.get('GopBurstMode', False),
                'GopPassThrough': output.get('GopPassThrough', 'Disabled'),
                'IgnoreTextInGraphics': output.get('IgnoreTextInGraphics', False),
                'InitialMode': output.get('InitialMode', 'Auto'),
                'ProvideConsoleGop': output.get('ProvideConsoleGop', True),
                'ReconnectGraphicsOnConnect': output.get('ReconnectGraphicsOnConnect', False),
                'ReconnectOnResChange': output.get('ReconnectOnResChange', False),
                'ReplaceTabWithSpace': output.get('ReplaceTabWithSpace', False),
                'SanitiseClearScreen': output.get('SanitiseClearScreen', False),
                'UgaPassThrough': output.get('UgaPassThrough', False)
            }
        
        # APFS settings
        if 'APFS' in uefi_config:
            apfs = uefi_config['APFS']
            uefi['UefiApfs'] = {
                'EnableJumpstart': apfs.get('EnableJumpstart', True),
                'GlobalConnect': apfs.get('GlobalConnect', False),
                'HideVerbose': apfs.get('HideVerbose', True),
                'JumpstartHotPlug': apfs.get('JumpstartHotPlug', False),
                'MinDate': apfs.get('MinDate', 0),
                'MinVersion': apfs.get('MinVersion', 0)
            }
        
        # ConnectDrivers
        if 'ConnectDrivers' in uefi_config:
            uefi['ConnectDrivers'] = uefi_config['ConnectDrivers']
        
        # Quirks
        if 'Quirks' in uefi_config:
            quirks = uefi_config['Quirks']
            uefi['UefiQuirks'] = {
                'ActivateHpetSupport': quirks.get('ActivateHpetSupport', False),
                'DisableSecurityPolicy': quirks.get('DisableSecurityPolicy', False),
                'EnableVectorAcceleration': quirks.get('EnableVectorAcceleration', True),
                'EnableVmx': quirks.get('EnableVmx', False),
                'ExitBootServicesDelay': quirks.get('ExitBootServicesDelay', 0),
                'ForceOcWriteFlash': quirks.get('ForceOcWriteFlash', False),
                'ForgeUefiSupport': quirks.get('ForgeUefiSupport', False),
                'IgnoreInvalidFlexRatio': quirks.get('IgnoreInvalidFlexRatio', False),
                'ReleaseUsbOwnership': quirks.get('ReleaseUsbOwnership', False),
                'ReloadOptionRoms': quirks.get('ReloadOptionRoms', False),
                'RequestBootVarRouting': quirks.get('RequestBootVarRouting', True),
                'ResizeGpuBars': quirks.get('ResizeGpuBars', -1),
                'ResizeUsePciRbIo': quirks.get('ResizeUsePciRbIo', False),
                'ShimRetainProtocol': quirks.get('ShimRetainProtocol', False),
                'TscSyncTimeout': quirks.get('TscSyncTimeout', 0),
                'UnblockFsConnect': quirks.get('UnblockFsConnect', False)
            }
    
    return uefi

def extract_device_properties(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract DeviceProperties.Add"""
    if 'DeviceProperties' in config and 'Add' in config['DeviceProperties']:
        return config['DeviceProperties']['Add']
    return {}

def extract_acpi_quirks(config: Dict[str, Any]) -> Dict[str, Any]:
    """Extract ACPI.Quirks"""
    if 'ACPI' in config and 'Quirks' in config['ACPI']:
        return config['ACPI']['Quirks']
    return {}

def detect_amd_patches(patches: List[Dict[str, Any]]) -> bool:
    """Detect if AMD Vanilla patches are present"""
    for patch in patches:
        comment = patch.get('Comment', '').lower()
        if 'amd' in comment or 'algrey' in comment or 'cpuid_cores_per_package' in comment:
            return True
    return False

def convert_plist_to_changeset(plist_path: Path, output_name: str = "") -> Dict[str, Any]:
    """Convert a config.plist to changeset format"""
    
    log(f"Loading plist: {plist_path}")
    config = load_plist(plist_path)
    
    if not config:
        error("Failed to load or parse plist file")
        return {}
    
    log("Extracting changeset data from plist...")
    
    changeset = {}
    
    # Extract all components
    acpi_add = extract_acpi_add(config)
    if acpi_add:
        changeset['AcpiAdd'] = acpi_add
        log(f"Found {len(acpi_add)} ACPI files")
    
    kexts = extract_kexts(config)
    if kexts:
        changeset['Kexts'] = kexts
        log(f"Found {len(kexts)} kexts")
    
    booter_quirks = extract_booter_quirks(config)
    if booter_quirks:
        changeset['BooterQuirks'] = booter_quirks
        log(f"Found {len(booter_quirks)} booter quirks")
    
    kernel_quirks = extract_kernel_quirks(config)
    if kernel_quirks:
        changeset['KernelQuirks'] = kernel_quirks
        log(f"Found {len(kernel_quirks)} kernel quirks")
    
    kernel_emulate = extract_kernel_emulate(config)
    if kernel_emulate:
        changeset['KernelEmulate'] = kernel_emulate
        log(f"Found kernel emulation settings")
    
    kernel_patches = extract_kernel_patches(config)
    if kernel_patches:
        # Check if AMD patches are present
        if detect_amd_patches(kernel_patches):
            changeset['AmdVanillaPatches'] = False
            log("Detected AMD Vanilla patches - using AmdVanillaPatches flag")
        else:
            changeset['KernelPatches'] = kernel_patches
            log(f"Found {len(kernel_patches)} kernel patches")
    
    platform_info = extract_platform_info(config)
    if platform_info:
        changeset['PlatformInfo'] = platform_info
        log("Found PlatformInfo configuration")
    
    boot_args = extract_boot_args(config)
    if boot_args:
        changeset['BootArgs'] = boot_args
        log(f"Found boot args: {boot_args}")
    
    nvram = extract_nvram(config)
    if nvram:
        changeset['Nvram'] = nvram
        log("Found NVRAM configuration")
    
    misc_settings = extract_misc_settings(config)
    for key, value in misc_settings.items():
        changeset[key] = value
    
    uefi_drivers = extract_uefi_drivers(config)
    if uefi_drivers:
        changeset['UefiDrivers'] = uefi_drivers
        log(f"Found {len(uefi_drivers)} UEFI drivers")
    
    uefi_settings = extract_uefi_settings(config)
    for key, value in uefi_settings.items():
        changeset[key] = value
    
    device_properties = extract_device_properties(config)
    if device_properties:
        changeset['DeviceProperties'] = device_properties
        log("Found device properties")
    
    acpi_quirks = extract_acpi_quirks(config)
    if acpi_quirks:
        changeset['AcpiQuirks'] = acpi_quirks
        log(f"Found {len(acpi_quirks)} ACPI quirks")
    
    return changeset

def save_changeset(changeset: Dict[str, Any], output_path: Path) -> bool:
    """Save changeset to YAML file"""
    try:
        # Convert bytes objects to strings to avoid !!binary YAML formatting
        changeset_converted = convert_bytes_to_strings(changeset)
        
        with open(output_path, 'w') as f:
            yaml.safe_dump(changeset_converted, f, default_flow_style=False, sort_keys=False, indent=2)
        log(f"Saved changeset to: {output_path}")
        return True
    except Exception as e:
        error(f"Failed to save changeset: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Convert OpenCore config.plist to changeset format',
        epilog='''
Examples:
  # Convert a plist to changeset
  python3.11 scripts/plist-to-changeset.py assets/Working.Proxmox.config.plist working-proxmox
  
  # Use force to overwrite existing changeset
  python3.11 scripts/plist-to-changeset.py assets/Working.Proxmox.config.plist working-proxmox --force
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('plist_path', help='Path to the config.plist file')
    parser.add_argument('changeset_name', help='Output changeset name (without .yaml extension)')
    parser.add_argument('--force', '-f', action='store_true', help='Overwrite existing changeset')
    
    args = parser.parse_args()
    
    # Validate input file
    plist_path = Path(args.plist_path)
    if not plist_path.exists():
        error(f"Plist file not found: {plist_path}")
        return 1
    
    # Use the provided changeset name
    output_name = args.changeset_name
    
    # Remove .yaml extension if provided
    if output_name.endswith('.yaml'):
        output_name = output_name[:-5]
    
    output_path = ROOT / "config" / "changesets" / f"{output_name}.yaml"
    
    # Check if output exists
    if output_path.exists() and not args.force:
        error(f"Changeset already exists: {output_path}")
        error("Use --force to overwrite")
        return 1
    
    # Convert plist to changeset
    changeset = convert_plist_to_changeset(plist_path, output_name)
    
    if not changeset:
        error("Failed to convert plist to changeset")
        return 1
    
    # Save changeset
    if save_changeset(changeset, output_path):
        info(f"Successfully converted {plist_path} to {output_path}")
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
