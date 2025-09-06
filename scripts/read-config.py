#!/usr/bin/env python3.11

import sys
import plistlib
import yaml
import base64
from pathlib import Path

def read_config_plist(plist_path):
    """Read and parse an OpenCore config.plist file into changeset YAML format"""
    
    with open(plist_path, 'rb') as f:
        config = plistlib.load(f)
    
    # Initialize the output structure
    output = {}
    
    # Extract Kexts
    if 'Kernel' in config and 'Add' in config['Kernel']:
        kexts = []
        for kext in config['Kernel']['Add']:
            if kext.get('Enabled', False):
                kext_entry = {
                    'bundle': kext.get('BundlePath', ''),
                    'exec': ''
                }
                
                # Extract executable name from ExecutablePath
                exec_path = kext.get('ExecutablePath', '')
                if exec_path and exec_path != '' and exec_path.startswith('Contents/MacOS/'):
                    kext_entry['exec'] = exec_path.replace('Contents/MacOS/', '')
                
                kexts.append(kext_entry)
        
        if kexts:
            output['kexts'] = kexts
    
    # Extract Booter Quirks
    if 'Booter' in config and 'Quirks' in config['Booter']:
        booter_quirks = {}
        booter = config['Booter']['Quirks']
        
        # Only include non-default values
        quirk_defaults = {
            'AllowRelocationBlock': False,
            'AvoidRuntimeDefrag': False,
            'ClearTaskSwitchBit': False,
            'DevirtualiseMmio': False,
            'DisableSingleUser': False,
            'DisableVariableWrite': False,
            'DiscardHibernateMap': False,
            'EnableSafeModeSlide': False,
            'EnableWriteUnprotector': False,
            'FixupAppleEfiImages': True,
            'ForceBooterSignature': False,
            'ForceExitBootServices': False,
            'ProtectMemoryRegions': False,
            'ProtectSecureBoot': False,
            'ProtectUefiServices': False,
            'ProvideCustomSlide': False,
            'ProvideMaxSlide': 0,
            'RebuildAppleMemoryMap': False,
            'ResizeAppleGpuBars': -1,
            'SetupVirtualMap': True,
            'SignalAppleOS': False,
            'SyncRuntimePermissions': False
        }
        
        for key, default_value in quirk_defaults.items():
            if key in booter and booter[key] != default_value:
                booter_quirks[key] = booter[key]
        
        if booter_quirks:
            output['booter_quirks'] = booter_quirks
    
    # Extract Kernel Quirks
    if 'Kernel' in config and 'Quirks' in config['Kernel']:
        kernel_quirks = {}
        kernel = config['Kernel']['Quirks']
        
        # Only include non-default values
        quirk_defaults = {
            'AppleCpuPmCfgLock': False,
            'AppleXcpmCfgLock': False,
            'AppleXcpmExtraMsrs': False,
            'AppleXcpmForceBoost': False,
            'CustomPciSerialDevice': False,
            'CustomSMBIOSGuid': False,
            'DisableIoMapper': False,
            'DisableIoMapperMapping': False,
            'DisableLinkeditJettison': False,
            'DisableRtcChecksum': False,
            'ExtendBTFeatureFlags': False,
            'ExternalDiskIcons': False,
            'ForceAquantiaEthernet': False,
            'ForceSecureBootScheme': False,
            'IncreasePciBarSize': False,
            'LapicKernelPanic': False,
            'LegacyCommpage': False,
            'PanicNoKextDump': False,
            'PowerTimeoutKernelPanic': False,
            'ProvideCurrentCpuInfo': False,
            'SetApfsTrimTimeout': -1,
            'ThirdPartyDrives': False,
            'XhciPortLimit': False
        }
        
        for key, default_value in quirk_defaults.items():
            if key in kernel and kernel[key] != default_value:
                kernel_quirks[key] = kernel[key]
        
        if kernel_quirks:
            output['kernel_quirks'] = kernel_quirks
    
    # Extract Kernel Emulate
    if 'Kernel' in config and 'Emulate' in config['Kernel']:
        emulate = config['Kernel']['Emulate']
        kernel_emulate = {}
        
        if emulate.get('DummyPowerManagement', False):
            kernel_emulate['DummyPowerManagement'] = True
        
        if kernel_emulate:
            output['kernel_emulate'] = kernel_emulate
    
    # Extract ACPI Quirks
    if 'ACPI' in config and 'Quirks' in config['ACPI']:
        acpi_quirks = {}
        acpi = config['ACPI']['Quirks']
        
        # Only include non-default values
        quirk_defaults = {
            'FadtEnableReset': False,
            'NormalizeHeaders': False,
            'RebaseRegions': False,
            'ResetHwSig': False,
            'ResetLogoStatus': False,
            'SyncTableIds': False
        }
        
        for key, default_value in quirk_defaults.items():
            if key in acpi and acpi[key] != default_value:
                acpi_quirks[key] = acpi[key]
        
        if acpi_quirks:
            output['acpi_quirks'] = acpi_quirks
    
    # Extract Boot Args
    if ('NVRAM' in config and 'Add' in config['NVRAM'] and 
        '7C436110-AB2A-4BBB-A880-FE41995C9F82' in config['NVRAM']['Add']):
        nvram_add = config['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']
        if 'boot-args' in nvram_add:
            output['boot_args'] = nvram_add['boot-args']
    
    # Extract CSR Active Config
    if ('NVRAM' in config and 'Add' in config['NVRAM'] and 
        '7C436110-AB2A-4BBB-A880-FE41995C9F82' in config['NVRAM']['Add']):
        nvram_add = config['NVRAM']['Add']['7C436110-AB2A-4BBB-A880-FE41995C9F82']
        if 'csr-active-config' in nvram_add:
            csr_data = nvram_add['csr-active-config']
            if isinstance(csr_data, bytes):
                output['csr_active_config'] = csr_data.hex().upper().zfill(8)
    
    # Extract Security Settings
    if 'Misc' in config and 'Security' in config['Misc']:
        security = config['Misc']['Security']
        
        if 'SecureBootModel' in security and security['SecureBootModel'] != 'Default':
            output['secureboot_model'] = security['SecureBootModel']
        
        if 'Vault' in security and security['Vault'] != 'Secure':
            output['vault'] = security['Vault']
        
        if 'ScanPolicy' in security:
            output['scan_policy'] = security['ScanPolicy']
    
    # Extract Misc Boot Settings
    if 'Misc' in config and 'Boot' in config['Misc']:
        boot = config['Misc']['Boot']
        misc_boot = {}
        
        # Only include non-default values
        boot_defaults = {
            'HideAuxiliary': False,
            'ShowPicker': True,
            'Timeout': 5,
            'PickerMode': 'Builtin',
            'PickerAttributes': 1,
            'TakeoffDelay': 0,
            'HibernateMode': 'None',
            'LauncherOption': 'Disabled',
            'LauncherPath': 'Default'
        }
        
        for key, default_value in boot_defaults.items():
            if key in boot and boot[key] != default_value:
                misc_boot[key] = boot[key]
        
        if misc_boot:
            output['misc_boot'] = misc_boot
    
    # Extract Tools
    if 'Misc' in config and 'Tools' in config['Misc']:
        tools = []
        for tool in config['Misc']['Tools']:
            if tool.get('Enabled', False):
                tool_entry = {
                    'Name': tool.get('Name', ''),
                    'Path': tool.get('Path', ''),
                    'Enabled': True,
                    'Auxiliary': tool.get('Auxiliary', True)
                }
                tools.append(tool_entry)
        
        if tools:
            output['tools'] = tools
    
    # Extract ACPI Add files
    if 'ACPI' in config and 'Add' in config['ACPI']:
        acpi_add = []
        for acpi_file in config['ACPI']['Add']:
            if acpi_file.get('Enabled', False):
                acpi_add.append(acpi_file.get('Path', ''))
        
        if acpi_add:
            output['acpi_add'] = acpi_add
    
    # Extract Device Properties
    if 'DeviceProperties' in config and 'Add' in config['DeviceProperties']:
        device_props = config['DeviceProperties']['Add']
        if device_props:
            # Convert any data values back to readable format
            converted_props = {}
            for device, props in device_props.items():
                converted_props[device] = {}
                for key, value in props.items():
                    if isinstance(value, bytes):
                        # Convert bytes to hex representation
                        converted_props[device][key] = f"0x{value.hex().upper()}"
                    else:
                        converted_props[device][key] = value
            
            if converted_props:
                output['device_properties'] = converted_props
    
    # Extract UEFI Drivers
    if 'UEFI' in config and 'Drivers' in config['UEFI']:
        drivers = []
        for driver in config['UEFI']['Drivers']:
            if driver.get('Enabled', False):
                driver_entry = {
                    'path': driver.get('Path', ''),
                    'enabled': True,
                    'load_early': driver.get('LoadEarly', False),
                    'arguments': driver.get('Arguments', ''),
                    'comment': driver.get('Comment', '')
                }
                drivers.append(driver_entry)
        
        if drivers:
            output['uefi_drivers'] = drivers
    
    # Extract SMBIOS
    if 'PlatformInfo' in config and 'Generic' in config['PlatformInfo']:
        generic = config['PlatformInfo']['Generic']
        smbios = {}
        
        if 'SystemProductName' in generic:
            smbios['SystemProductName'] = generic['SystemProductName']
        if 'SystemSerialNumber' in generic:
            smbios['SystemSerialNumber'] = generic['SystemSerialNumber']
        if 'MLB' in generic:
            smbios['MLB'] = generic['MLB']
        if 'SystemUUID' in generic:
            smbios['SystemUUID'] = generic['SystemUUID']
        if 'ROM' in generic:
            rom_data = generic['ROM']
            if isinstance(rom_data, bytes):
                # Convert to list of integers
                smbios['ROM'] = list(rom_data)
        
        if smbios:
            output['smbios'] = smbios
    
    return output

def main():
    if len(sys.argv) != 2:
        print("Usage: python3 read-config.py <config.plist>")
        sys.exit(1)
    
    plist_path = sys.argv[1]
    
    if not Path(plist_path).exists():
        print(f"Error: File {plist_path} not found")
        sys.exit(1)
    
    try:
        config_data = read_config_plist(plist_path)
        
        # Output as YAML
        yaml_output = yaml.dump(config_data, default_flow_style=False, sort_keys=False)
        print(yaml_output)
        
    except Exception as e:
        print(f"Error reading config: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
