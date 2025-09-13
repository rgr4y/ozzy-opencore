#!/usr/bin/env python3.11
"""
Compare two changesets and show differences.

This script compares changesets and shows what's different between them.
"""

import sys
import argparse
import yaml
from pathlib import Path
from typing import Dict, Any, Set, List

# Import our common libraries
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import ROOT, log, warn, error, info, load_changeset

def deep_diff(dict1: Dict[str, Any], dict2: Dict[str, Any], path: str = "") -> List[str]:
    """Compare two dictionaries and return list of differences"""
    differences = []
    
    # Get all keys from both dictionaries
    all_keys = set(dict1.keys()) | set(dict2.keys())
    
    for key in sorted(all_keys):
        current_path = f"{path}.{key}" if path else key
        
        if key not in dict1:
            differences.append(f"+ {current_path}: {dict2[key]} (only in second)")
        elif key not in dict2:
            differences.append(f"- {current_path}: {dict1[key]} (only in first)")
        elif dict1[key] != dict2[key]:
            val1, val2 = dict1[key], dict2[key]
            
            # If both are dictionaries, recurse
            if isinstance(val1, dict) and isinstance(val2, dict):
                differences.extend(deep_diff(val1, val2, current_path))
            else:
                differences.append(f"~ {current_path}: {val1} -> {val2}")
    
    return differences

def compare_changesets(changeset1_path: Path, changeset2_path: Path) -> Dict[str, Any]:
    """Compare two changesets and return detailed differences"""
    
    # Load changesets
    try:
        with open(changeset1_path, 'r') as f:
            changeset1 = yaml.safe_load(f)
    except Exception as e:
        error(f"Failed to load {changeset1_path}: {e}")
        return {}
    
    try:
        with open(changeset2_path, 'r') as f:
            changeset2 = yaml.safe_load(f)
    except Exception as e:
        error(f"Failed to load {changeset2_path}: {e}")
        return {}
    
    # Get all sections from both changesets
    all_sections = set(changeset1.keys()) | set(changeset2.keys())
    
    comparison = {
        'sections_only_in_first': [],
        'sections_only_in_second': [],
        'different_sections': {},
        'identical_sections': [],
        'summary': {}
    }
    
    for section in sorted(all_sections):
        if section not in changeset1:
            comparison['sections_only_in_second'].append(section)
        elif section not in changeset2:
            comparison['sections_only_in_first'].append(section)
        elif changeset1[section] != changeset2[section]:
            # Section exists in both but is different
            differences = []
            
            if isinstance(changeset1[section], dict) and isinstance(changeset2[section], dict):
                differences = deep_diff(changeset1[section], changeset2[section])
            elif isinstance(changeset1[section], list) and isinstance(changeset2[section], list):
                # Compare lists
                if len(changeset1[section]) != len(changeset2[section]):
                    differences.append(f"Length: {len(changeset1[section])} -> {len(changeset2[section])}")
                
                # Compare each item
                max_len = max(len(changeset1[section]), len(changeset2[section]))
                for i in range(max_len):
                    if i >= len(changeset1[section]):
                        differences.append(f"[{i}]: (missing) -> {changeset2[section][i]}")
                    elif i >= len(changeset2[section]):
                        differences.append(f"[{i}]: {changeset1[section][i]} -> (missing)")
                    elif changeset1[section][i] != changeset2[section][i]:
                        differences.append(f"[{i}]: {changeset1[section][i]} -> {changeset2[section][i]}")
            else:
                differences.append(f"{changeset1[section]} -> {changeset2[section]}")
            
            comparison['different_sections'][section] = differences
        else:
            comparison['identical_sections'].append(section)
    
    # Generate summary
    comparison['summary'] = {
        'total_sections_first': len(changeset1),
        'total_sections_second': len(changeset2),
        'sections_only_in_first': len(comparison['sections_only_in_first']),
        'sections_only_in_second': len(comparison['sections_only_in_second']),
        'different_sections': len(comparison['different_sections']),
        'identical_sections': len(comparison['identical_sections'])
    }
    
    return comparison

def print_comparison_report(comparison: Dict[str, Any], name1: str, name2: str):
    """Print a detailed comparison report"""
    
    print(f"\n{'='*80}")
    print(f"CHANGESET COMPARISON REPORT")
    print(f"{'='*80}")
    print(f"First changeset:  {name1}")
    print(f"Second changeset: {name2}")
    print(f"{'='*80}")
    
    summary = comparison['summary']
    print(f"\nSUMMARY:")
    print(f"  Sections in first:     {summary['total_sections_first']}")
    print(f"  Sections in second:    {summary['total_sections_second']}")
    print(f"  Only in first:         {summary['sections_only_in_first']}")
    print(f"  Only in second:        {summary['sections_only_in_second']}")
    print(f"  Different:             {summary['different_sections']}")
    print(f"  Identical:             {summary['identical_sections']}")
    
    # Identical sections
    if comparison['identical_sections']:
        print(f"\n✅ IDENTICAL SECTIONS:")
        for section in comparison['identical_sections']:
            print(f"  ✓ {section}")

    # Sections only in first
    if comparison['sections_only_in_first']:
        print(f"\n📋 SECTIONS ONLY IN FIRST ({name1}):")
        for section in comparison['sections_only_in_first']:
            print(f"  - {section}")
    
    # Sections only in second
    if comparison['sections_only_in_second']:
        print(f"\n📋 SECTIONS ONLY IN SECOND ({name2}):")
        for section in comparison['sections_only_in_second']:
            print(f"  + {section}")
    
    # Different sections
    if comparison['different_sections']:
        print(f"\n🔄 DIFFERENT SECTIONS:")
        for section, differences in comparison['different_sections'].items():
            print(f"\n  📁 {section}:")
            for diff in differences:
                if diff.startswith('+'):
                    print(f"    🟢 {diff}")
                elif diff.startswith('-'):
                    print(f"    🔴 {diff}")
                elif diff.startswith('~'):
                    print(f"    🟡 {diff}")
                else:
                    print(f"    ⚪ {diff}")
    
def main():
    parser = argparse.ArgumentParser(
        description='Compare two OpenCore changesets',
        epilog='''
Examples:
  # Compare two changesets
  python3.11 scripts/compare-changesets.py proxmox_ryzen3950x_nogpu working-proxmox-converted
  
  # Compare with existing changeset
  python3.11 scripts/compare-changesets.py ryzen3950x_rx580_AMDVanilla working-proxmox-converted
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('changeset1', help='First changeset name (without .yaml extension)')
    parser.add_argument('changeset2', help='Second changeset name (without .yaml extension)')
    
    args = parser.parse_args()
    
    # Build paths
    changeset1_path = ROOT / "config" / "changesets" / f"{args.changeset1}.yaml"
    changeset2_path = ROOT / "config" / "changesets" / f"{args.changeset2}.yaml"
    
    # Check if files exist
    if not changeset1_path.exists():
        error(f"Changeset not found: {changeset1_path}")
        return 1
    
    if not changeset2_path.exists():
        error(f"Changeset not found: {changeset2_path}")
        return 1
    
    # Compare changesets
    log("Comparing changesets...")
    comparison = compare_changesets(changeset1_path, changeset2_path)
    
    if not comparison:
        error("Failed to compare changesets")
        return 1
    
    # Print report
    print_comparison_report(comparison, args.changeset1, args.changeset2)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
