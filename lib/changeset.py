#!/usr/bin/env python3
"""
Changeset management and processing utilities for OpenCore configurations.

This module provides functionality for loading, validating, and processing
OpenCore configuration changesets.
"""

import yaml
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional

# Import common utilities
sys.path.append(str(Path(__file__).parent))
from common import ROOT, log, warn, error, get_changeset_path, list_available_changesets
from data_conversion import convert_changeset_data_types

def load_changeset(changeset_name: str) -> Optional[Dict[str, Any]]:
    """Load a changeset from file"""
    changeset_path = get_changeset_path(changeset_name)
    
    if not changeset_path.exists():
        error(f"Changeset not found: {changeset_path}")
        return None
    
    try:
        with open(changeset_path, 'r') as f:
            changeset_data = yaml.safe_load(f)
        log(f"Loaded changeset: {changeset_name}")
        return changeset_data
    except Exception as e:
        error(f"Failed to load changeset {changeset_name}: {e}")
        return None

def save_changeset(changeset_name: str, changeset_data: Dict[str, Any], backup: bool = True) -> bool:
    """Save changeset data to file"""
    changeset_path = get_changeset_path(changeset_name)
    
    # Create backup if requested
    if backup and changeset_path.exists():
        backup_path = changeset_path.with_suffix('.yaml.backup')
        try:
            import shutil
            shutil.copy2(changeset_path, backup_path)
            log(f"Created backup: {backup_path}")
        except Exception as e:
            warn(f"Failed to create backup: {e}")
    
    try:
        with open(changeset_path, 'w') as f:
            yaml.safe_dump(changeset_data, f, default_flow_style=False, sort_keys=False)
        log(f"Saved changeset: {changeset_name}")
        return True
    except Exception as e:
        error(f"Failed to save changeset {changeset_name}: {e}")
        return False

def validate_changeset_structure(changeset_data: Dict[str, Any]) -> Dict[str, List[str]]:
    """Validate changeset structure and return any issues"""
    issues = {
        'errors': [],
        'warnings': [],
        'info': []
    }
    
    # Check for required sections
    required_sections = ['kexts', 'booter_quirks', 'kernel_quirks']
    for section in required_sections:
        if section not in changeset_data:
            issues['warnings'].append(f"Missing recommended section: {section}")
    
    # Validate kexts section
    if 'kexts' in changeset_data:
        kexts = changeset_data['kexts']
        if not isinstance(kexts, list):
            issues['errors'].append("kexts section must be a list")
        else:
            for i, kext in enumerate(kexts):
                if not isinstance(kext, dict):
                    issues['errors'].append(f"kext[{i}] must be a dictionary")
                    continue
                if 'bundle' not in kext:
                    issues['errors'].append(f"kext[{i}] missing 'bundle' field")
                if 'exec' not in kext:
                    issues['warnings'].append(f"kext[{i}] missing 'exec' field")
    
    # Validate SMBIOS section
    if 'smbios' in changeset_data:
        smbios = changeset_data['smbios']
        if not isinstance(smbios, dict):
            issues['errors'].append("smbios section must be a dictionary")
        else:
            required_smbios_fields = [
                'SystemProductName', 'SystemSerialNumber', 
                'MLB', 'SystemUUID', 'ROM'
            ]
            for field in required_smbios_fields:
                if field not in smbios:
                    issues['warnings'].append(f"SMBIOS missing field: {field}")
    
    # Validate device properties
    if 'device_properties' in changeset_data:
        device_props = changeset_data['device_properties']
        if not isinstance(device_props, dict):
            issues['errors'].append("device_properties section must be a dictionary")
    
    # Check for Proxmox configuration
    if 'proxmox_vm' in changeset_data:
        issues['info'].append("Changeset includes Proxmox VM configuration")
    
    return issues

def get_changeset_summary(changeset_data: Dict[str, Any]) -> Dict[str, Any]:
    """Get a summary of changeset contents"""
    summary = {
        'sections': list(changeset_data.keys()),
        'kext_count': 0,
        'has_smbios': False,
        'has_device_properties': False,
        'has_proxmox_config': False,
        'boot_args': None,
        'model': None
    }
    
    if 'kexts' in changeset_data and isinstance(changeset_data['kexts'], list):
        summary['kext_count'] = len(changeset_data['kexts'])
    
    if 'smbios' in changeset_data:
        summary['has_smbios'] = True
        smbios = changeset_data['smbios']
        if isinstance(smbios, dict):
            summary['model'] = smbios.get('SystemProductName')
    
    if 'device_properties' in changeset_data:
        summary['has_device_properties'] = True
    
    if 'proxmox_vm' in changeset_data:
        summary['has_proxmox_config'] = True
    
    if 'boot_args' in changeset_data:
        summary['boot_args'] = changeset_data['boot_args']
    
    return summary

def compare_changesets(changeset1_name: str, changeset2_name: str) -> Dict[str, Any]:
    """Compare two changesets and return differences"""
    changeset1 = load_changeset(changeset1_name)
    changeset2 = load_changeset(changeset2_name)
    
    if not changeset1 or not changeset2:
        return {'error': 'Failed to load one or both changesets'}
    
    differences = {
        'sections_only_in_1': [],
        'sections_only_in_2': [],
        'different_sections': {},
        'identical_sections': []
    }
    
    all_sections = set(changeset1.keys()) | set(changeset2.keys())
    
    for section in all_sections:
        if section in changeset1 and section not in changeset2:
            differences['sections_only_in_1'].append(section)
        elif section in changeset2 and section not in changeset1:
            differences['sections_only_in_2'].append(section)
        elif changeset1[section] != changeset2[section]:
            differences['different_sections'][section] = {
                'changeset1': changeset1[section],
                'changeset2': changeset2[section]
            }
        else:
            differences['identical_sections'].append(section)
    
    return differences

def merge_changesets(base_changeset_name: str, overlay_changeset_name: str, output_name: str) -> bool:
    """Merge two changesets, with overlay taking precedence"""
    base_data = load_changeset(base_changeset_name)
    overlay_data = load_changeset(overlay_changeset_name)
    
    if not base_data or not overlay_data:
        return False
    
    # Start with base data
    merged_data = base_data.copy()
    
    # Overlay the second changeset
    for section, section_data in overlay_data.items():
        if section in merged_data:
            if isinstance(section_data, dict) and isinstance(merged_data[section], dict):
                # Merge dictionaries
                merged_data[section].update(section_data)
            elif isinstance(section_data, list) and isinstance(merged_data[section], list):
                # For lists, overlay completely replaces base
                merged_data[section] = section_data
            else:
                # For other types, overlay replaces base
                merged_data[section] = section_data
        else:
            # New section from overlay
            merged_data[section] = section_data
    
    return save_changeset(output_name, merged_data)

def extract_changeset_section(changeset_name: str, section_name: str) -> Optional[Any]:
    """Extract a specific section from a changeset"""
    changeset_data = load_changeset(changeset_name)
    if not changeset_data:
        return None
    
    return changeset_data.get(section_name)

def update_changeset_section(changeset_name: str, section_name: str, section_data: Any, backup: bool = True) -> bool:
    """Update a specific section in a changeset"""
    changeset_data = load_changeset(changeset_name)
    if not changeset_data:
        return False
    
    changeset_data[section_name] = section_data
    return save_changeset(changeset_name, changeset_data, backup)

def remove_changeset_section(changeset_name: str, section_name: str, backup: bool = True) -> bool:
    """Remove a section from a changeset"""
    changeset_data = load_changeset(changeset_name)
    if not changeset_data:
        return False
    
    if section_name in changeset_data:
        del changeset_data[section_name]
        return save_changeset(changeset_name, changeset_data, backup)
    
    warn(f"Section '{section_name}' not found in changeset")
    return True

def list_changeset_kexts(changeset_name: str) -> List[Dict[str, str]]:
    """List all kexts in a changeset"""
    changeset_data = load_changeset(changeset_name)
    if not changeset_data or 'kexts' not in changeset_data:
        return []
    
    kexts = changeset_data['kexts']
    if not isinstance(kexts, list):
        return []
    
    return [
        {
            'bundle': kext.get('bundle', 'Unknown'),
            'exec': kext.get('exec', ''),
            'enabled': kext.get('enabled', True)
        }
        for kext in kexts if isinstance(kext, dict)
    ]

def validate_kext_availability(changeset_name: str) -> Dict[str, bool]:
    """Check if all kexts in changeset are available in assets"""
    from common import get_project_paths
    
    paths = get_project_paths()
    kexts_dir = paths['efi_oc'] / 'Kexts'
    
    changeset_kexts = list_changeset_kexts(changeset_name)
    availability = {}
    
    for kext_info in changeset_kexts:
        kext_name = kext_info['bundle']
        kext_path = kexts_dir / kext_name
        availability[kext_name] = kext_path.exists()
    
    return availability
