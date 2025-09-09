#!/usr/bin/env python3
"""
Compare two OpenCore config.plist files and show differences in their resolved values.

This script loads two plist files and compares their contents, showing:
- Values that differ between the two files
- Values present in one but not the other
- Binary data differences with base64 representation
"""

import sys
import argparse
import plistlib
import base64
from pathlib import Path
from typing import Dict, Any, List, Union, Tuple, Optional

# Import our common libraries
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import ROOT, log, warn, error, info

def load_plist(plist_path: Path) -> Dict[str, Any]:
    """Load a plist file and return its contents"""
    try:
        with open(plist_path, 'rb') as f:
            return plistlib.load(f)
    except Exception as e:
        error(f"Failed to load plist {plist_path}: {e}")
        return {}

def format_value(value: Any) -> str:
    """Format a value for display, handling binary data specially"""
    if isinstance(value, bytes):
        if len(value) == 0:
            return "<empty bytes>"
        elif len(value) <= 32:  # Show short binary as base64
            return f"<bytes: {base64.b64encode(value).decode('ascii')}>"
        else:  # Show long binary as length
            return f"<bytes: {len(value)} bytes>"
    elif isinstance(value, bool):
        return str(value).lower()
    elif isinstance(value, (int, float)):
        return str(value)
    elif isinstance(value, str):
        if len(value) > 100:
            return f'"{value[:97]}..."'
        return f'"{value}"'
    elif isinstance(value, (list, dict)):
        return f"<{type(value).__name__}: {len(value)} items>"
    else:
        return str(value)

def get_nested_value(data: Dict[str, Any], path: List[str]) -> Tuple[Any, bool]:
    """Get a nested value from a dictionary using a path. Returns (value, exists)"""
    current = data
    try:
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            elif isinstance(current, list) and key.isdigit():
                idx = int(key)
                if 0 <= idx < len(current):
                    current = current[idx]
                else:
                    return None, False
            else:
                return None, False
        return current, True
    except (KeyError, TypeError, ValueError):
        return None, False

def collect_all_paths(data: Any, current_path: Optional[List[str]] = None) -> List[List[str]]:
    """Recursively collect all paths in a nested structure"""
    if current_path is None:
        current_path = []
    
    paths = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            new_path = current_path + [key]
            paths.append(new_path)
            if isinstance(value, (dict, list)):
                # For arrays that need special handling, don't drill into individual elements
                if isinstance(value, list) and should_compare_array_as_whole(new_path):
                    # Just add the array path itself, don't recurse into elements
                    continue
                else:
                    paths.extend(collect_all_paths(value, new_path))
    elif isinstance(data, list):
        for idx, value in enumerate(data):
            new_path = current_path + [str(idx)]
            paths.append(new_path)
            if isinstance(value, (dict, list)):
                paths.extend(collect_all_paths(value, new_path))
    
    return paths

def should_compare_array_as_whole(path: List[str]) -> bool:
    """Check if an array should be compared as a whole rather than element by element"""
    path_str = ' -> '.join(path) if path else ''
    
    # Arrays that should be compared as wholes (after sorting)
    whole_array_paths = [
        'Kernel -> Add',
        'UEFI -> Drivers', 
        'Misc -> Tools',
        'ACPI -> Add'
    ]
    
    return path_str in whole_array_paths

def normalize_array_for_comparison(arr: List[Any], path: List[str]) -> List[Any]:
    """Normalize an array for comparison by sorting it appropriately"""
    if not isinstance(arr, list) or len(arr) == 0:
        return arr
    
    # Check if this is a kext/driver array that should be sorted
    path_str = ' -> '.join(path) if path else ''
    
    # Sort kext arrays by BundlePath
    if 'Kernel' in path_str and 'Add' in path_str:
        try:
            return sorted(arr, key=lambda x: x.get('BundlePath', '') if isinstance(x, dict) else str(x))
        except (TypeError, AttributeError):
            pass
    
    # Sort driver arrays by Path
    elif 'UEFI' in path_str and 'Drivers' in path_str:
        try:
            return sorted(arr, key=lambda x: x.get('Path', '') if isinstance(x, dict) else str(x))
        except (TypeError, AttributeError):
            pass
    
    # Sort tool arrays by Path
    elif 'Misc' in path_str and 'Tools' in path_str:
        try:
            return sorted(arr, key=lambda x: x.get('Path', '') if isinstance(x, dict) else str(x))
        except (TypeError, AttributeError):
            pass
    
    # For other arrays, try to sort if all elements are comparable
    try:
        if all(isinstance(x, (str, int, float, bool)) for x in arr):
            return sorted(arr)
        elif all(isinstance(x, dict) for x in arr):
            # Sort dicts by their string representation as fallback
            return sorted(arr, key=lambda x: str(sorted(x.items())) if isinstance(x, dict) else str(x))
    except (TypeError, AttributeError):
        pass
    
    # Return original if we can't sort
    return arr

def values_equal(val1: Any, val2: Any, path: Optional[List[str]] = None) -> bool:
    """Compare two values, handling different types appropriately"""
    # Handle None/missing values
    if val1 is None and val2 is None:
        return True
    if val1 is None or val2 is None:
        return False
    
    # Handle bytes comparison
    if isinstance(val1, bytes) and isinstance(val2, bytes):
        return val1 == val2
    
    # Handle array comparison with normalization
    if isinstance(val1, list) and isinstance(val2, list):
        if path and should_compare_array_as_whole(path):
            # Compare arrays after normalizing them
            norm_val1 = normalize_array_for_comparison(val1, path)
            norm_val2 = normalize_array_for_comparison(val2, path)
            return norm_val1 == norm_val2
        else:
            return val1 == val2
    
    # Handle type mismatches (e.g., string vs bytes)
    if type(val1) != type(val2):
        # Try converting bytes to base64 string for comparison
        if isinstance(val1, bytes) and isinstance(val2, str):
            return base64.b64encode(val1).decode('ascii') == val2
        elif isinstance(val1, str) and isinstance(val2, bytes):
            return val1 == base64.b64encode(val2).decode('ascii')
        return False
    
    # Regular comparison for same types
    return val1 == val2

def compare_arrays_ignore_comments(arr1: List[Any], arr2: List[Any]) -> bool:
    """Compare two arrays of dictionaries, ignoring Comment fields"""
    if len(arr1) != len(arr2):
        return False
    
    for item1, item2 in zip(arr1, arr2):
        if isinstance(item1, dict) and isinstance(item2, dict):
            # Create copies without Comment field
            item1_no_comment = {k: v for k, v in item1.items() if k != 'Comment'}
            item2_no_comment = {k: v for k, v in item2.items() if k != 'Comment'}
            if item1_no_comment != item2_no_comment:
                return False
        else:
            if item1 != item2:
                return False
    
    return True

def should_ignore_path(path: List[str]) -> bool:
    """Check if a path should be ignored in comparison"""
    if len(path) == 1:
        # Ignore top-level comment keys
        key = path[0]
        if key.startswith('#') or key == '#Generated':
            return True
    return False

def compare_plists(plist1: Dict[str, Any], plist2: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Compare two plist dictionaries and return differences"""
    
    # Collect all unique paths from both plists
    paths1 = set(tuple(path) for path in collect_all_paths(plist1))
    paths2 = set(tuple(path) for path in collect_all_paths(plist2))
    all_paths = paths1 | paths2
    
    differences = {
        'changed': [],
        'only_in_first': [],
        'only_in_second': [],
        'type_mismatch': []
    }
    
    for path_tuple in sorted(all_paths):
        path = list(path_tuple)
        path_str = ' -> '.join(path)
        
        # Skip ignored paths
        if should_ignore_path(path):
            continue
        
        val1, exists1 = get_nested_value(plist1, path)
        val2, exists2 = get_nested_value(plist2, path)
        
        if exists1 and exists2:
            if not values_equal(val1, val2, path):
                differences['changed'].append({
                    'path': path_str,
                    'plist1_value': format_value(val1),
                    'plist2_value': format_value(val2),
                    'raw_values': (val1, val2)
                })
        elif exists1 and not exists2:
            differences['only_in_first'].append({
                'path': path_str,
                'value': format_value(val1),
                'raw_value': val1
            })
        elif exists2 and not exists1:
            differences['only_in_second'].append({
                'path': path_str,
                'value': format_value(val2),
                'raw_value': val2
            })
    
    return differences

def print_differences(differences: Dict[str, List[Dict[str, Any]]], plist1_path: str, plist2_path: str):
    """Print the differences in a clean, hierarchical format"""
    
    print(f"\n=== Comparing LF: {Path(plist1_path).name} vs RF: {Path(plist2_path).name} ===\n")
    
    # Combine all differences and organize by section
    all_diffs = []
    
    # Add changed values
    for diff in differences['changed']:
        all_diffs.append({
            'path': diff['path'],
            'type': 'changed',
            'lf_value': diff['plist1_value'],
            'rf_value': diff['plist2_value']
        })
    
    # Add LF-only values
    for diff in differences['only_in_first']:
        all_diffs.append({
            'path': diff['path'],
            'type': 'lf_only',
            'value': diff['value']
        })
    
    # Add RF-only values
    for diff in differences['only_in_second']:
        all_diffs.append({
            'path': diff['path'],
            'type': 'rf_only',
            'value': diff['value']
        })
    
    if not all_diffs:
        print("✅ No differences found! The plists are functionally identical.")
        return
    
    # Group differences by top-level section
    sections = {}
    for diff in all_diffs:
        path_parts = diff['path'].split(' -> ')
        section = path_parts[0]
        
        if section not in sections:
            sections[section] = []
        sections[section].append(diff)
    
    # Print each section
    for section_name, section_diffs in sorted(sections.items()):
        # Count types for this section
        changed_in_section = [d for d in section_diffs if d['type'] == 'changed']
        lf_only_in_section = [d for d in section_diffs if d['type'] == 'lf_only']
        rf_only_in_section = [d for d in section_diffs if d['type'] == 'rf_only']
        
        # Skip sections that only have structural differences (dict->dict, list->list)
        meaningful_changes = []
        for diff in changed_in_section:
            if not (diff['lf_value'] in ['dict', 'list'] and diff['rf_value'] in ['dict', 'list']):
                meaningful_changes.append(diff)
        
        # Skip sections with no meaningful content
        if not meaningful_changes and not lf_only_in_section and not rf_only_in_section:
            continue
            
        print(f"📁 {section_name} -> {len(meaningful_changes)} changed, {len(lf_only_in_section)} LF-only, {len(rf_only_in_section)} RF-only")
        
        # Show important changes first
        important_diffs = meaningful_changes + lf_only_in_section
        shown_rf_count = 0
        max_rf_show = 3
        
        for diff in important_diffs:
            path_parts = diff['path'].split(' -> ')
            
            # Create indented path (skip the section name)
            if len(path_parts) > 1:
                sub_path = ' -> '.join(path_parts[1:])
                indent = "   "
            else:
                sub_path = "(root)"
                indent = "   "
            
            if diff['type'] == 'changed':
                # Show both values briefly
                lf_short = format_short_value(diff['lf_value'])
                rf_short = format_short_value(diff['rf_value'])
                print(f"{indent}{sub_path}: {lf_short} -> {rf_short}")
            elif diff['type'] == 'lf_only':
                print(f"{indent}{sub_path}: LF only")
        
        # Show limited RF-only items
        for diff in rf_only_in_section:
            if shown_rf_count < max_rf_show:
                path_parts = diff['path'].split(' -> ')
                if len(path_parts) > 1:
                    sub_path = ' -> '.join(path_parts[1:])
                    indent = "   "
                else:
                    sub_path = "(root)"
                    indent = "   "
                print(f"{indent}{sub_path}: RF only")
                shown_rf_count += 1
            elif shown_rf_count == max_rf_show:
                print(f"   ... and {len(rf_only_in_section) - max_rf_show} more RF-only items")
                break
        
        print()  # Empty line between sections
    
    # Brief summary
    total_diffs = len(all_diffs)
    changed_count = len(differences['changed'])
    lf_only_count = len(differences['only_in_first'])
    rf_only_count = len(differences['only_in_second'])
    
    print(f"📊 {total_diffs} differences: {changed_count} changed, {lf_only_count} LF-only, {rf_only_count} RF-only")

def format_short_value(value_str: str) -> str:
    """Format a value string for brief display"""
    if value_str.startswith('"') and value_str.endswith('"') and len(value_str) > 20:
        # Truncate long strings
        return f'"{value_str[1:15]}..."'
    elif value_str.startswith('<') and 'items>' in value_str:
        # Show just the container type
        if 'dict:' in value_str:
            return 'dict'
        elif 'list:' in value_str:
            return 'list'
    elif value_str.startswith('<bytes:'):
        # Show just 'bytes'
        return 'bytes'
    elif len(value_str) > 25:
        return f"{value_str[:22]}..."
    
    return value_str

def main():
    parser = argparse.ArgumentParser(
        description='Compare two OpenCore config.plist files and show differences',
        epilog='''
Examples:
  python3 scripts/compare-plists.py original.plist converted.plist
  python3 scripts/compare-plists.py assets/Working.Proxmox.config.plist out/build/efi/EFI/OC/config.plist
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('plist1', type=Path, help='Path to first plist file')
    parser.add_argument('plist2', type=Path, help='Path to second plist file')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show verbose output')
    parser.add_argument('--binary-details', '-b', action='store_true', help='Show detailed binary data comparisons')
    
    args = parser.parse_args()
    
    # Validate input files
    if not args.plist1.exists():
        error(f"First plist file not found: {args.plist1}")
        sys.exit(1)
    
    if not args.plist2.exists():
        error(f"Second plist file not found: {args.plist2}")
        sys.exit(1)
    
    # Load both plists
    log(f"Loading first plist: {args.plist1}")
    plist1 = load_plist(args.plist1)
    if not plist1:
        sys.exit(1)
    
    log(f"Loading second plist: {args.plist2}")
    plist2 = load_plist(args.plist2)
    if not plist2:
        sys.exit(1)
    
    # Compare the plists
    log("Comparing plists...")
    differences = compare_plists(plist1, plist2)
    
    # Print results
    print_differences(differences, str(args.plist1), str(args.plist2))

if __name__ == '__main__':
    main()
