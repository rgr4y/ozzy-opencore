#!/usr/bin/env python3.11
"""
SMBIOS generation and validation utilities for OpenCore configurations.

This module provides functionality for generating and validating SMBIOS data
including serial numbers, MLB, and UUIDs.
"""

import subprocess
import re
import uuid
import sys
from pathlib import Path
from typing import Dict, Tuple, Optional, Any

# Import common utilities
sys.path.append(str(Path(__file__).parent))
from common import ROOT, log, warn, error, validate_file_exists

def check_macserial_available() -> bool:
    """Check if macserial utility is available"""
    macserial_path = ROOT / "out" / "opencore" / "Utilities" / "macserial" / "macserial"
    return macserial_path.exists()

def get_macserial_path() -> Path:
    """Get path to macserial utility"""
    macserial_path = ROOT / "out" / "opencore" / "Utilities" / "macserial" / "macserial"
    validate_file_exists(macserial_path, "macserial utility")
    return macserial_path

def generate_smbios_data(model: str = "iMacPro1,1") -> Tuple[str, str]:
    """Generate SMBIOS data using macserial utility"""
    macserial_path = get_macserial_path()
    
    # Run macserial to generate serial and MLB for specific model
    cmd = [str(macserial_path), "-m", model]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"macserial failed: {result.stderr}")
    
    # Parse output - format without -a flag is: "Serial | MLB" (one per line)
    output = result.stdout.strip()
    lines = output.split('\n')
    
    # Get the first valid line with a pipe separator
    for line in lines:
        line = line.strip()
        if '|' in line:
            parts = line.split('|')
            if len(parts) >= 2:
                # Without -a flag: parts[0] = Serial, parts[1] = MLB
                serial = parts[0].strip()
                mlb = parts[1].strip()
                return serial, mlb
    
    raise RuntimeError(f"Could not parse macserial output: {output}")

def generate_uuid() -> str:
    """Generate a random UUID"""
    return str(uuid.uuid4()).upper()

def generate_mac_address() -> bytes:
    """Generate a random MAC address with Apple OUI"""
    # Use Apple's OUI: 00:17:F2 (one of many Apple uses)
    apple_oui = [0x00, 0x17, 0xF2]
    # Generate random last 3 bytes
    import random
    random_bytes = [random.randint(0, 255) for _ in range(3)]
    return bytes(apple_oui + random_bytes)

# Placeholder patterns to identify values that need generation
PLACEHOLDER_PATTERNS = {
    'serial': [
        r'^[A-Z0-9]{10,12}$',  # Generic placeholder pattern
        'iMacPro1,1',          # Default model name
        'C02XD1WJHX87',        # Common placeholder
        'PLACEHOLDER',         # Explicit placeholder
        'XXX',                 # Simple placeholder
    ],
    'mlb': [
        r'^[A-Z0-9]{17}$',     # Generic MLB pattern
        'C02309XXXXHX87XX',    # Common placeholder
        'PLACEHOLDER',         # Explicit placeholder
        'XXX',                 # Simple placeholder
    ],
    'uuid': [
        '12345678-1234-1234-1234-123456789ABC',  # Common placeholder
        'PLACEHOLDER',                            # Explicit placeholder
        '00000000-0000-0000-0000-000000000000',  # Zero UUID
    ]
}

def is_placeholder_value(value: str, value_type: str) -> bool:
    """Check if a value is a placeholder that should be replaced"""
    if not value or value.strip() == '':
        return True
    
    value = value.strip()
    patterns = PLACEHOLDER_PATTERNS.get(value_type, [])
    
    for pattern in patterns:
        if isinstance(pattern, str):
            if value == pattern:
                return True
        else:
            # It's a regex pattern
            if re.match(pattern, value) and 'PLACEHOLDER' in value.upper():
                return True
    
    return False

def is_placeholder_serial(serial: str) -> bool:
    """Check if serial number is a placeholder"""
    return is_placeholder_value(serial, 'serial')

def is_placeholder_mlb(mlb: str) -> bool:
    """Check if MLB is a placeholder"""
    return is_placeholder_value(mlb, 'mlb')

def is_placeholder_uuid(uuid_str: str) -> bool:
    """Check if UUID is a placeholder"""
    return is_placeholder_value(uuid_str, 'uuid')

def is_placeholder_rom(rom_value: Any) -> bool:
    """Check if ROM value is a placeholder"""
    if isinstance(rom_value, list):
        # Check for common placeholder patterns
        placeholder_patterns = [
            [17, 34, 51, 68, 85, 102],      # Sequential test pattern
            [0, 0, 0, 0, 0, 0],             # All zeros
            [255, 255, 255, 255, 255, 255], # All ones
        ]
        return rom_value in placeholder_patterns
    elif isinstance(rom_value, str):
        placeholder_strings = [
            "11:22:33:44:55:66",
            "00:00:00:00:00:00",
            "FF:FF:FF:FF:FF:FF",
            "PLACEHOLDER",
        ]
        return rom_value.upper() in [p.upper() for p in placeholder_strings]
    elif isinstance(rom_value, bytes):
        return is_placeholder_rom(list(rom_value))
    
    return False

def get_smbios_section(changeset_data: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Get SMBIOS section from changeset data, supporting both new and legacy formats
    
    Returns:
        Tuple of (smbios_dict, section_path) where section_path indicates which structure was found
    """
    if 'PlatformInfo' in changeset_data and 'Generic' in changeset_data['PlatformInfo']:
        return changeset_data['PlatformInfo']['Generic'], 'PlatformInfo.Generic'
    elif 'smbios' in changeset_data:
        return changeset_data['smbios'], 'smbios'
    else:
        return None, None

def _validate_and_generate_smbios_selective(
    changeset_data: Dict[str, Any], 
    force: bool = False,
    update_serial: bool = True,
    update_mlb: bool = True,
    update_uuid: bool = True,
    update_rom: bool = True
) -> bool:
    """Generic SMBIOS generation function that can selectively generate fields"""
    smbios, section_path = get_smbios_section(changeset_data)
    
    if not smbios:
        warn("No PlatformInfo.Generic or SMBIOS section found in changeset")
        return False
    
    log(f"Using {section_path} for SMBIOS data")
    
    model = smbios.get('SystemProductName', 'iMacPro1,1')
    current_serial = smbios.get('SystemSerialNumber', '')
    current_mlb = smbios.get('MLB', '')
    current_uuid = smbios.get('SystemUUID', '')
    current_rom = smbios.get('ROM', [])
    
    # Check what needs generation based on what we're supposed to generate
    checks = []
    if update_serial:
        checks.append(is_placeholder_serial(current_serial))
    if update_mlb:
        checks.append(is_placeholder_mlb(current_mlb))
    if update_uuid:
        checks.append(is_placeholder_uuid(current_uuid))
    if update_rom:
        checks.append(is_placeholder_rom(current_rom))
    
    needs_generation = force or any(checks)
    
    if not needs_generation:
        fields = []
        if update_serial: fields.append("serial")
        if update_mlb: fields.append("MLB")
        if update_uuid: fields.append("UUID")
        if update_rom: fields.append("ROM")
        log(f"{' and '.join(fields)} appear to be real (not placeholder)")
        warn(f"No changes made. Use --force to regenerate {' and '.join(fields)} anyway")
        return False
    
    # Only check macserial if we need to generate serial/MLB
    if (update_serial or update_mlb) and not check_macserial_available():
        error("macserial utility not available. Please run './ozzy fetch' first.")
        return False
    
    try:
        # Build description of what we're generating
        generating = []
        if update_serial: generating.append("serial")
        if update_mlb: generating.append("MLB")
        if update_uuid: generating.append("UUID")
        if update_rom: generating.append("ROM")
        
        preserving = []
        if not update_serial: preserving.append("serial")
        if not update_mlb: preserving.append("MLB")
        if not update_uuid: preserving.append("UUID")
        if not update_rom: preserving.append("ROM")
        
        if preserving:
            log(f"Generating {' and '.join(generating)} only (preserving {' and '.join(preserving)})")
        else:
            log(f"Generating all SMBIOS data for model: {model}")
        
        # Generate serial and MLB if needed
        new_serial, new_mlb = current_serial, current_mlb
        if update_serial or update_mlb:
            new_serial, new_mlb = generate_smbios_data(model)
            if update_serial:
                log(f"Generated Serial: {new_serial}")
            else:
                new_serial = current_serial
                log(f"Preserving Serial: {current_serial}")
            
            if update_mlb:
                log(f"Generated MLB: {new_mlb}")
            else:
                new_mlb = current_mlb
                log(f"Preserving MLB: {current_mlb}")
        else:
            log(f"Preserving Serial: {current_serial}")
            log(f"Preserving MLB: {current_mlb}")
        
        # Generate UUID if needed
        new_uuid = current_uuid
        if update_uuid:
            new_uuid = generate_uuid()
            log(f"Generated UUID: {new_uuid}")
        else:
            log(f"Preserving UUID: {current_uuid}")
        
        # Generate ROM if needed
        new_rom = current_rom
        if update_rom:
            new_rom_bytes = generate_mac_address()
            # Store as hex string (e.g., "0017F2ED84E1")
            new_rom = new_rom_bytes.hex().upper()
            log(f"Generated ROM: {':'.join(f'{b:02X}' for b in new_rom_bytes)} ({new_rom})")
        else:
            if isinstance(current_rom, str):
                log(f"Preserving ROM: {current_rom}")
            elif isinstance(current_rom, list):
                # Convert list back to hex string for consistency
                new_rom = ''.join(f"{b:02X}" for b in current_rom)
                rom_display = ':'.join(f"{b:02X}" for b in current_rom)
                log(f"Preserving ROM: {rom_display} ({new_rom})")
            else:
                log(f"Preserving ROM: {current_rom}")
        
        # Update changeset data
        smbios['SystemSerialNumber'] = new_serial
        smbios['MLB'] = new_mlb
        smbios['SystemUUID'] = new_uuid
        smbios['ROM'] = new_rom  # This will be a hex string
        
        # Also update NVRAM section if it exists and copying is enabled
        copy_to_nvram = changeset_data.get('PlatformInfoGenericCopyToNvramForAppleId', True)
        if copy_to_nvram and 'Nvram' in changeset_data and 'add' in changeset_data['Nvram']:
            apple_guid = '4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14'
            if apple_guid in changeset_data['Nvram']['add']:
                nvram_section = changeset_data['Nvram']['add'][apple_guid]
                nvram_section['SystemSerialNumber'] = new_serial
                nvram_section['MLB'] = new_mlb
                nvram_section['SystemUUID'] = new_uuid
                # For NVRAM, store as hex string too (the data conversion layer will handle base64)
                nvram_section['ROM'] = new_rom
                
                if preserving:
                    log(f"Updated NVRAM section with new {' and '.join(generating)} (preserved {' and '.join(preserving)})")
                else:
                    log("Updated NVRAM section with new SMBIOS data")
        
        return True
        
    except Exception as e:
        error(f"Failed to generate SMBIOS data: {e}")
        return False

def validate_and_generate_smbios(changeset_data: Dict[str, Any], force: bool = False) -> bool:
    """Validate SMBIOS data and generate new values if needed"""
    return _validate_and_generate_smbios_selective(
        changeset_data, force, 
        update_serial=True, update_mlb=True, update_uuid=True, update_rom=True
    )

def validate_and_generate_serial_mlb_only(changeset_data: Dict[str, Any], force: bool = False) -> bool:
    """Validate SMBIOS data and generate new serial and MLB only, preserving UUID and ROM"""
    return _validate_and_generate_smbios_selective(
        changeset_data, force,
        update_serial=True, update_mlb=True, update_uuid=False, update_rom=False
    )

def validate_and_generate_rom_uuid_only(changeset_data: Dict[str, Any], force: bool = False) -> bool:
    """Validate SMBIOS data and generate new ROM and UUID only, preserving serial and MLB"""
    return _validate_and_generate_smbios_selective(
        changeset_data, force,
        update_serial=False, update_mlb=False, update_uuid=True, update_rom=True
    )

def get_smbios_info(changeset_data: Dict[str, Any]) -> Dict[str, str]:
    """Get current SMBIOS information from changeset"""
    smbios, section_path = get_smbios_section(changeset_data)
    
    if not smbios:
        return {}
    
    rom_value = smbios.get('ROM', [])
    
    # Format ROM for display - show compact hex format
    if isinstance(rom_value, list):
        # Convert list of integers to hex string
        rom_display = ''.join(f"{b:02X}" for b in rom_value)
    elif isinstance(rom_value, bytes):
        rom_display = rom_value.hex().upper()
    elif isinstance(rom_value, str):
        # Assume it's already in hex format, clean it up
        rom_display = rom_value.replace(':', '').upper()
    else:
        rom_display = str(rom_value)
    
    return {
        'model': smbios.get('SystemProductName', 'Not set'),
        'serial': smbios.get('SystemSerialNumber', 'Not set'),
        'mlb': smbios.get('MLB', 'Not set'),
        'uuid': smbios.get('SystemUUID', 'Not set'),
        'rom': rom_display
    }

def validate_smbios_format(smbios_data: Dict[str, Any]) -> Dict[str, bool]:
    """Validate SMBIOS data format"""
    validation_results = {}
    
    # Validate serial number format
    serial = smbios_data.get('SystemSerialNumber', '')
    validation_results['serial_format'] = bool(re.match(r'^[A-Z0-9]{10,12}$', serial))
    
    # Validate MLB format  
    mlb = smbios_data.get('MLB', '')
    validation_results['mlb_format'] = bool(re.match(r'^[A-Z0-9]{17}$', mlb))
    
    # Validate UUID format
    uuid_str = smbios_data.get('SystemUUID', '')
    try:
        uuid.UUID(uuid_str)
        validation_results['uuid_format'] = True
    except:
        validation_results['uuid_format'] = False
    
    # Validate ROM format
    rom_value = smbios_data.get('ROM', [])
    if isinstance(rom_value, list):
        validation_results['rom_format'] = (
            len(rom_value) == 6 and 
            all(isinstance(b, int) and 0 <= b <= 255 for b in rom_value)
        )
    else:
        validation_results['rom_format'] = False
    
    return validation_results
