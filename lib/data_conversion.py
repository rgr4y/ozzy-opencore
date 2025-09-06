#!/usr/bin/env python3.11
"""
Data conversion and manipulation utilities for OpenCore configurations.

This module handles the conversion between different data formats used in
OpenCore configuration files, changesets, and plist files.
"""

import base64
import json
from typing import Any, Dict, List, Union

class CustomJSONEncoder(json.JSONEncoder):
    """Custom JSON encoder that handles bytes objects"""
    def default(self, obj):
        if isinstance(obj, bytes):
            return list(obj)
        return super().default(obj)

def convert_data_values(obj: Any) -> Any:
    """Convert data values to proper format for plist handling"""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == 'built-in' and isinstance(value, list):
                # Convert integer array to bytes for built-in property
                result[key] = bytes(value)
            elif key == 'ROM' and isinstance(value, list):
                # Convert integer array to bytes for ROM
                result[key] = bytes(value)
            elif isinstance(value, str) and key == 'ROM':
                # Handle hex string conversion for ROM
                try:
                    # Remove any spaces and convert hex to bytes
                    hex_str = value.replace(' ', '')
                    result[key] = bytes.fromhex(hex_str)
                except ValueError:
                    result[key] = value
            else:
                result[key] = convert_data_values(value)
        return result
    elif isinstance(obj, list):
        return [convert_data_values(item) for item in obj]
    else:
        return obj

def bytes_to_hex_string(data: bytes) -> str:
    """Convert bytes to hex string representation"""
    return data.hex().upper()

def hex_string_to_bytes(hex_str: str) -> bytes:
    """Convert hex string to bytes"""
    # Remove any spaces and convert to bytes
    hex_str = hex_str.replace(' ', '').replace('0x', '')
    return bytes.fromhex(hex_str)

def int_list_to_bytes(int_list: List[int]) -> bytes:
    """Convert list of integers to bytes"""
    return bytes(int_list)

def bytes_to_int_list(data: bytes) -> List[int]:
    """Convert bytes to list of integers"""
    return list(data)

def base64_encode(data: bytes) -> str:
    """Encode bytes as base64 string"""
    return base64.b64encode(data).decode('ascii')

def base64_decode(b64_str: str) -> bytes:
    """Decode base64 string to bytes"""
    return base64.b64decode(b64_str)

def normalize_rom_value(rom_value: Union[str, List[int], bytes]) -> bytes:
    """Normalize ROM value to bytes format"""
    if isinstance(rom_value, str):
        return hex_string_to_bytes(rom_value)
    elif isinstance(rom_value, list):
        return int_list_to_bytes(rom_value)
    elif isinstance(rom_value, bytes):
        return rom_value
    else:
        raise ValueError(f"Unsupported ROM value type: {type(rom_value)}")

def normalize_data_field(data_value: Any) -> bytes:
    """Normalize various data field formats to bytes"""
    if isinstance(data_value, bytes):
        return data_value
    elif isinstance(data_value, str):
        # Try base64 first, then hex
        try:
            return base64_decode(data_value)
        except:
            try:
                return hex_string_to_bytes(data_value)
            except:
                raise ValueError(f"Cannot convert string to bytes: {data_value}")
    elif isinstance(data_value, list):
        return int_list_to_bytes(data_value)
    else:
        raise ValueError(f"Unsupported data field type: {type(data_value)}")

def validate_mac_address(mac_addr: Union[str, List[int], bytes]) -> bool:
    """Validate MAC address format"""
    try:
        if isinstance(mac_addr, str):
            # Remove common separators
            mac_clean = mac_addr.replace(':', '').replace('-', '').replace(' ', '')
            if len(mac_clean) != 12:
                return False
            bytes.fromhex(mac_clean)
        elif isinstance(mac_addr, list):
            if len(mac_addr) != 6:
                return False
            for byte_val in mac_addr:
                if not (0 <= byte_val <= 255):
                    return False
        elif isinstance(mac_addr, bytes):
            if len(mac_addr) != 6:
                return False
        else:
            return False
        return True
    except:
        return False

def format_mac_address(mac_addr: Union[str, List[int], bytes], separator: str = ':') -> str:
    """Format MAC address with specified separator"""
    if isinstance(mac_addr, str):
        mac_clean = mac_addr.replace(':', '').replace('-', '').replace(' ', '')
        mac_bytes = bytes.fromhex(mac_clean)
    elif isinstance(mac_addr, list):
        mac_bytes = bytes(mac_addr)
    elif isinstance(mac_addr, bytes):
        mac_bytes = mac_addr
    else:
        raise ValueError(f"Unsupported MAC address type: {type(mac_addr)}")
    
    return separator.join(f"{b:02X}" for b in mac_bytes)

def convert_changeset_data_types(changeset_data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert changeset data types for proper plist handling"""
    converted = {}
    
    for section_name, section_data in changeset_data.items():
        if section_name == 'smbios' and isinstance(section_data, dict):
            # Handle SMBIOS data conversion
            converted_smbios = {}
            for key, value in section_data.items():
                if key == 'ROM':
                    converted_smbios[key] = normalize_rom_value(value)
                else:
                    converted_smbios[key] = value
            converted[section_name] = converted_smbios
        elif section_name == 'device_properties' and isinstance(section_data, dict):
            # Handle device properties data conversion
            converted_props = {}
            for device_path, properties in section_data.items():
                converted_device_props = {}
                for prop_name, prop_value in properties.items():
                    if isinstance(prop_value, list) and all(isinstance(x, int) for x in prop_value):
                        converted_device_props[prop_name] = bytes(prop_value)
                    else:
                        converted_device_props[prop_name] = prop_value
                converted_props[device_path] = converted_device_props
            converted[section_name] = converted_props
        else:
            converted[section_name] = convert_data_values(section_data)
    
    return converted

def prepare_json_serializable(data: Any) -> Any:
    """Prepare data for JSON serialization by converting bytes to lists"""
    if isinstance(data, dict):
        return {key: prepare_json_serializable(value) for key, value in data.items()}
    elif isinstance(data, list):
        return [prepare_json_serializable(item) for item in data]
    elif isinstance(data, bytes):
        return list(data)
    else:
        return data
