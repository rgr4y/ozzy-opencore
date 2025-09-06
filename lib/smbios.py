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
    
    # Run macserial to generate serial and MLB
    cmd = [str(macserial_path), "-a", "-m", model]
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise RuntimeError(f"macserial failed: {result.stderr}")
    
    # Parse output - format is typically: "Type: Serial | MLB"
    output = result.stdout.strip()
    lines = output.split('\n')
    
    for line in lines:
        if model in line and '|' in line:
            parts = line.split('|')
            if len(parts) >= 2:
                serial = parts[0].split(':')[-1].strip()
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

def validate_and_generate_smbios(changeset_data: Dict[str, Any], force: bool = False) -> bool:
    """Validate SMBIOS data and generate new values if needed"""
    if 'smbios' not in changeset_data:
        warn("No SMBIOS section found in changeset")
        return False
    
    smbios = changeset_data['smbios']
    model = smbios.get('SystemProductName', 'iMacPro1,1')
    current_serial = smbios.get('SystemSerialNumber', '')
    current_mlb = smbios.get('MLB', '')
    current_uuid = smbios.get('SystemUUID', '')
    current_rom = smbios.get('ROM', [])
    
    needs_generation = force or any([
        is_placeholder_serial(current_serial),
        is_placeholder_mlb(current_mlb),
        is_placeholder_uuid(current_uuid),
        is_placeholder_rom(current_rom)
    ])
    
    if not needs_generation:
        log("SMBIOS data appears to be real (not placeholder)")
        return True
    
    if not check_macserial_available():
        error("macserial utility not available. Please run './ozzy fetch' first.")
        return False
    
    try:
        log(f"Generating SMBIOS data for model: {model}")
        
        # Generate serial and MLB
        new_serial, new_mlb = generate_smbios_data(model)
        log(f"Generated Serial: {new_serial}")
        log(f"Generated MLB: {new_mlb}")
        
        # Generate UUID
        new_uuid = generate_uuid()
        log(f"Generated UUID: {new_uuid}")
        
        # Generate ROM (MAC address)
        new_rom = generate_mac_address()
        log(f"Generated ROM: {new_rom.hex().upper()}")
        
        # Update changeset data
        smbios['SystemSerialNumber'] = new_serial
        smbios['MLB'] = new_mlb
        smbios['SystemUUID'] = new_uuid
        smbios['ROM'] = list(new_rom)  # Store as list for YAML serialization
        
        return True
        
    except Exception as e:
        error(f"Failed to generate SMBIOS data: {e}")
        return False

def get_smbios_info(changeset_data: Dict[str, Any]) -> Dict[str, str]:
    """Get current SMBIOS information from changeset"""
    if 'smbios' not in changeset_data:
        return {}
    
    smbios = changeset_data['smbios']
    rom_value = smbios.get('ROM', [])
    
    # Format ROM for display
    if isinstance(rom_value, list):
        rom_display = ':'.join(f"{b:02X}" for b in rom_value)
    elif isinstance(rom_value, bytes):
        rom_display = ':'.join(f"{b:02X}" for b in rom_value)
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
