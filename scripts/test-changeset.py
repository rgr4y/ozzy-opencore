#!/usr/bin/env python3.11
"""
Test changeset parsing and validation.

This script tests that a changeset file can be loaded correctly and validates
its structure and content.
"""

import sys
import yaml
import argparse
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import (
    ROOT, log, warn, error, info,
    validate_changeset_exists, get_changeset_path
)

def test_changeset_parsing(changeset_name):
    """Test that the changeset is being parsed correctly"""
    log(f"Testing changeset parsing: {changeset_name}")
    
    # Validate changeset exists
    changeset_path = validate_changeset_exists(changeset_name)
    
    try:
        with open(changeset_path, 'r') as f:
            changeset_data = yaml.safe_load(f)
    except Exception as e:
        error(f"Failed to parse YAML: {e}")
        return False
    
    log("✓ Changeset loaded and parsed successfully")
    
    # Test basic structure
    if not isinstance(changeset_data, dict):
        error("Changeset root should be a dictionary")
        return False
    
    info(f"Changeset contains {len(changeset_data)} top-level sections:")
    for section in changeset_data.keys():
        info(f"  - {section}")
    
    # Test common sections
    test_results = []
    
    # Test kexts section
    if 'kexts' in changeset_data:
        result = test_kexts_section(changeset_data['kexts'])
        test_results.append(('kexts', result))
    
    # Test PlatformInfo section
    if 'platform_info' in changeset_data and 'generic' in changeset_data['platform_info']:
        result = test_smbios_section(changeset_data['platform_info']['generic'])
        test_results.append(('platform_info.generic', result))
    
    # Test legacy SMBIOS section
    elif 'smbios' in changeset_data:
        result = test_smbios_section(changeset_data['smbios'])
        test_results.append(('smbios (legacy)', result))
    
    # Test proxmox_vm section
    if 'proxmox_vm' in changeset_data:
        result = test_proxmox_section(changeset_data['proxmox_vm'])
        test_results.append(('proxmox_vm', result))
    
    # Test boot_args section
    if 'boot_args' in changeset_data:
        result = test_boot_args_section(changeset_data['boot_args'])
        test_results.append(('boot_args', result))
    
    # Summary
    log("Test Results Summary:")
    all_passed = True
    for section, passed in test_results:
        status = "✓" if passed else "✗"
        log(f"  {status} {section}")
        if not passed:
            all_passed = False
    
    return all_passed

def test_kexts_section(kexts_data):
    """Test kexts section structure"""
    log("Testing kexts section...")
    
    if not isinstance(kexts_data, list):
        error("kexts should be a list")
        return False
    
    info(f"Found {len(kexts_data)} kexts:")
    for i, kext in enumerate(kexts_data):
        if not isinstance(kext, dict):
            error(f"Kext {i} should be a dictionary")
            return False
        
        if 'bundle' not in kext:
            error(f"Kext {i} missing required 'bundle' field")
            return False
        
        bundle_name = kext['bundle']
        info(f"  - {bundle_name}")
        
        # Check if bundle exists in assets
        bundle_path = ROOT / 'assets' / 'kexts' / bundle_name
        if bundle_path.exists():
            info(f"    ✓ Found in assets")
        else:
            warn(f"    ! Not found in assets: {bundle_path}")
    
    return True

def test_smbios_section(smbios_data):
    """Test SMBIOS section structure"""
    log("Testing SMBIOS section...")
    
    if not isinstance(smbios_data, dict):
        error("smbios should be a dictionary")
        return False
    
    required_fields = ['SystemProductName', 'SystemSerialNumber', 'MLB', 'SystemUUID']
    for field in required_fields:
        if field not in smbios_data:
            error(f"Missing required SMBIOS field: {field}")
            return False
        info(f"  ✓ {field}: {smbios_data[field]}")
    
    # Check ROM field
    if 'ROM' in smbios_data:
        rom_data = smbios_data['ROM']
        if isinstance(rom_data, list) and len(rom_data) == 6:
            info(f"  ✓ ROM: {rom_data} (6 bytes)")
        else:
            warn(f"  ! ROM should be a 6-byte array, got: {rom_data}")
    
    return True

def test_boot_args_section(boot_args_data):
    """Test boot_args section"""
    log("Testing boot_args section...")
    
    if not isinstance(boot_args_data, str):
        error("boot_args should be a string")
        return False
    
    info(f"  Boot args: {boot_args_data}")
    
    # Check for common AMD flags
    if 'agdpmod=pikera' in boot_args_data:
        info("  ✓ Found AMD GPU patch flag")
    
    if '-v' in boot_args_data:
        info("  ✓ Verbose mode enabled")
    
    return True
    
    if 'assets' in proxmox_config:
        print(f"[*] Found {len(proxmox_config['assets'])} assets:")
        for asset in proxmox_config['assets']:
            src_relative = asset['src']
            dest_path = asset['dest']
            
            # Handle relative paths properly
            if src_relative.startswith('./'):
                src_path = ROOT / src_relative[2:]  # Remove "./" prefix
            else:
                src_path = ROOT / src_relative
            
            print(f"  - {src_relative} -> {dest_path}")
            print(f"    Resolved path: {src_path}")
            print(f"    Exists: {src_path.exists()}")
            if src_path.exists():
                print(f"    Size: {src_path.stat().st_size} bytes")
    
    if 'conf_overrides' in proxmox_config:
        print(f"[*] Found {len(proxmox_config['conf_overrides'])} configuration overrides:")
        for key, value in proxmox_config['conf_overrides'].items():
            print(f"  - {key} = {value}")
            if key == 'hostpci0':
                print(f"    ^^ This should contain romfile=/usr/share/kvm/RX580.rom")
    
    return True

def test_proxmox_section(proxmox_data):
    """Test proxmox_vm section structure"""
    log("Testing proxmox_vm section...")
    
    if not isinstance(proxmox_data, dict):
        error("proxmox_vm should be a dictionary")
        return False
    
    # Test assets subsection
    if 'assets' in proxmox_data:
        assets = proxmox_data['assets']
        if not isinstance(assets, list):
            error("proxmox_vm.assets should be a list")
            return False
        
        info(f"Found {len(assets)} Proxmox assets:")
        for asset in assets:
            if not isinstance(asset, dict):
                error("Each asset should be a dictionary")
                return False
            
            if 'src' not in asset or 'dest' not in asset:
                error("Each asset should have 'src' and 'dest' fields")
                return False
            
            src_relative = asset['src']
            dest_path = asset['dest']
            
            # Handle relative paths properly
            if src_relative.startswith('./'):
                src_path = ROOT / src_relative[2:]  # Remove "./" prefix
            else:
                src_path = ROOT / src_relative
            
            info(f"  - {src_relative} -> {dest_path}")
            if src_path.exists():
                size = src_path.stat().st_size
                info(f"    ✓ Source exists ({size} bytes)")
            else:
                warn(f"    ! Source not found: {src_path}")
    
    # Test conf_overrides subsection
    if 'conf_overrides' in proxmox_data:
        overrides = proxmox_data['conf_overrides']
        if not isinstance(overrides, dict):
            error("proxmox_vm.conf_overrides should be a dictionary")
            return False
        
        info(f"Found {len(overrides)} configuration overrides:")
        for key, value in overrides.items():
            info(f"  - {key} = {value}")
            if key == 'hostpci0' and 'romfile=' in str(value):
                info("    ✓ ROM file specified for GPU passthrough")
    
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Test changeset parsing and validation',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This script tests that a changeset can be loaded and parsed correctly,
and validates its structure and content.

Examples:
  python3.11 test-changeset.py myconfig
  python3.11 test-changeset.py ryzen3950x_rx580_AMDVanilla
        """
    )
    parser.add_argument('changeset', help='Changeset name (without .yaml extension)')
    
    args = parser.parse_args()
    
    try:
        if test_changeset_parsing(args.changeset):
            log("🎉 All changeset tests passed!")
            sys.exit(0)
        else:
            error("❌ Some changeset tests failed!")
            sys.exit(1)
    except KeyboardInterrupt:
        warn("Test cancelled by user")
        sys.exit(1)
    except Exception as e:
        error(f"Test failed with exception: {e}")
        sys.exit(1)
