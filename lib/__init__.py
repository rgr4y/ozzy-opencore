#!/usr/bin/env python3.11
"""
Init file for the OpenCore deployment library.

This module provides a unified import interface for all library components.
"""

# Import all commonly used functions and classes
from .common import (
    ROOT, Colors, log, warn, error, info,
    load_config, run_command, run_legacy,
    get_remote_config, scp, ssh,
    ensure_directory, read_json_file, write_json_file,
    find_files_by_pattern, cleanup_macos_metadata,
    validate_file_exists, get_project_paths,
    check_required_tools, get_changeset_path,
    list_available_changesets, list_newest_changesets, validate_changeset_exists
)

from .data_conversion import (
    CustomJSONEncoder, convert_data_values,
    bytes_to_hex_string, hex_string_to_bytes,
    int_list_to_bytes, bytes_to_int_list,
    base64_encode, base64_decode,
    normalize_rom_value, normalize_data_field,
    validate_mac_address, format_mac_address,
    convert_changeset_data_types, prepare_json_serializable
)

from .smbios import (
    check_macserial_available, get_macserial_path,
    generate_smbios_data, generate_uuid, generate_mac_address,
    is_placeholder_value, is_placeholder_serial,
    is_placeholder_mlb, is_placeholder_uuid, is_placeholder_rom,
    validate_and_generate_smbios, get_smbios_info,
    validate_smbios_format
)

from .changeset import (
    load_changeset, save_changeset,
    validate_changeset_structure, get_changeset_summary,
    compare_changesets, merge_changesets,
    extract_changeset_section, update_changeset_section,
    remove_changeset_section, list_changeset_kexts,
    validate_kext_availability
)

from .efi_builder import (
    build_complete_efi_structure, copy_efi_for_build
)

from .paths import paths

__version__ = "1.0.0"
__all__ = [
    # Common utilities
    'ROOT', 'Colors', 'log', 'warn', 'error', 'info',
    'load_config', 'run_command', 'run_legacy',
    'get_remote_config', 'scp', 'ssh',
    'ensure_directory', 'read_json_file', 'write_json_file',
    'find_files_by_pattern', 'cleanup_macos_metadata',
    'validate_file_exists', 'get_project_paths',
    'check_required_tools', 'get_changeset_path',
    'list_available_changesets', 'list_newest_changesets',
    
    # Data conversion
    'CustomJSONEncoder', 'convert_data_values',
    'bytes_to_hex_string', 'hex_string_to_bytes',
    'int_list_to_bytes', 'bytes_to_int_list',
    'base64_encode', 'base64_decode',
    'normalize_rom_value', 'normalize_data_field',
    'validate_mac_address', 'format_mac_address',
    'convert_changeset_data_types', 'prepare_json_serializable',
    
    # SMBIOS utilities
    'check_macserial_available', 'get_macserial_path',
    'generate_smbios_data', 'generate_uuid', 'generate_mac_address',
    'is_placeholder_value', 'is_placeholder_serial',
    'is_placeholder_mlb', 'is_placeholder_uuid', 'is_placeholder_rom',
    'validate_and_generate_smbios', 'get_smbios_info',
    'validate_smbios_format',
    
    # Changeset management
    'load_changeset', 'save_changeset',
    'validate_changeset_structure', 'get_changeset_summary',
    'compare_changesets', 'merge_changesets',
    'extract_changeset_section', 'update_changeset_section',
    'remove_changeset_section', 'list_changeset_kexts',
    'validate_kext_availability',
    
    # Path management
    'paths'
]
