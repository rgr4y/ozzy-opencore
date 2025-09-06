#!/usr/bin/env python3.11
"""
AMD Vanilla patch management script.

This script provides utilities for managing AMD Vanilla kernel patches,
including downloading, applying, and customizing them for specific CPU configurations.
"""

import sys
import argparse
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import ROOT, log, warn, error
from lib.changeset import (
    load_amd_vanilla_patches,
    modify_amd_core_count_patches,
    apply_amd_vanilla_patches_to_changeset,
    get_amd_vanilla_patch_info,
    list_available_changesets
)

def cmd_info(args):
    """Show information about AMD Vanilla patches"""
    info = get_amd_vanilla_patch_info()
    
    if 'error' in info:
        error(info['error'])
        return 1
    
    print(f"AMD Vanilla Patches Information")
    print(f"==============================")
    print(f"Total patches: {info['total_patches']}")
    print(f"Core count patches: {len(info['core_count_patches'])}")
    print(f"Other patches: {len(info['other_patches'])}")
    print(f"Darwin versions supported: {', '.join(info['darwin_versions'])}")
    
    if args.verbose:
        print(f"\nCore Count Patches:")
        for patch in info['core_count_patches']:
            print(f"  - {patch['comment']}")
            print(f"    Darwin: {patch['min_kernel']} - {patch['max_kernel']}")
            print(f"    Arch: {patch['arch']}, ID: {patch['identifier']}")
        
        print(f"\nOther Patches:")
        for patch in info['other_patches']:
            print(f"  - {patch['comment']}")
            print(f"    Darwin: {patch['min_kernel']} - {patch['max_kernel']}")
    
    return 0

def cmd_apply(args):
    """Apply AMD Vanilla patches to a changeset"""
    changeset_name = args.changeset
    core_count = args.cores
    
    if not changeset_name:
        error("Changeset name is required")
        return 1
    
    # Remove .yaml extension if provided
    if changeset_name.endswith('.yaml'):
        changeset_name = changeset_name[:-5]
    
    log(f"Applying AMD Vanilla patches to changeset '{changeset_name}' with {core_count} cores")
    
    if apply_amd_vanilla_patches_to_changeset(changeset_name, core_count, backup=not args.no_backup):
        log(f"✓ Successfully applied AMD Vanilla patches")
        return 0
    else:
        error("✗ Failed to apply AMD Vanilla patches")
        return 1

def cmd_list_changesets(args):
    """List available changesets"""
    changesets = list_available_changesets()
    
    if not changesets:
        warn("No changesets found")
        return 0
    
    print("Available changesets:")
    for changeset in changesets:
        print(f"  - {changeset}")
    
    return 0

def cmd_test_patches(args):
    """Test AMD patch modification without applying to changeset"""
    core_count = args.cores
    
    log(f"Testing AMD patch modification for {core_count} cores")
    
    # Load AMD Vanilla patches
    amd_patches = load_amd_vanilla_patches()
    if not amd_patches:
        return 1
    
    # Modify core count in patches
    modified_patches = modify_amd_core_count_patches(amd_patches, core_count)
    
    # Show what changed
    log("Patch modification results:")
    core_patches = [p for p in modified_patches if 'cpuid_cores_per_package' in p.get('Comment', '').lower()]
    
    for patch in core_patches:
        comment = patch.get('Comment', 'Unknown')
        replace_data = patch.get('Replace', b'')
        
        if isinstance(replace_data, bytes):
            hex_string = ' '.join(f'{b:02X}' for b in replace_data)
        elif isinstance(replace_data, str):
            # Assume base64
            import base64
            try:
                decoded = base64.b64decode(replace_data)
                hex_string = ' '.join(f'{b:02X}' for b in decoded)
            except:
                hex_string = replace_data
        else:
            hex_string = str(replace_data)
        
        print(f"  {comment}")
        print(f"    Replace: {hex_string}")
    
    return 0

def main():
    parser = argparse.ArgumentParser(
        description='AMD Vanilla patch management',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Show AMD Vanilla patch information
  ./amd-vanilla.py info
  
  # Apply AMD patches to a changeset for 16-core CPU
  ./amd-vanilla.py apply ryzen3950x_rx580_AMDVanilla --cores 16
  
  # Test patch modification without applying
  ./amd-vanilla.py test --cores 16
  
  # List available changesets
  ./amd-vanilla.py list
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Info command
    info_parser = subparsers.add_parser('info', help='Show AMD Vanilla patch information')
    info_parser.add_argument('-v', '--verbose', action='store_true', help='Show detailed patch information')
    
    # Apply command
    apply_parser = subparsers.add_parser('apply', help='Apply AMD Vanilla patches to changeset')
    apply_parser.add_argument('changeset', help='Changeset name (without .yaml extension)')
    apply_parser.add_argument('--cores', type=int, default=16, help='CPU core count (default: 16)')
    apply_parser.add_argument('--no-backup', action='store_true', help='Do not create backup of changeset')
    
    # Test command
    test_parser = subparsers.add_parser('test', help='Test patch modification without applying')
    test_parser.add_argument('--cores', type=int, default=16, help='CPU core count (default: 16)')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List available changesets')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Command dispatch
    commands = {
        'info': cmd_info,
        'apply': cmd_apply,
        'test': cmd_test_patches,
        'list': cmd_list_changesets
    }
    
    if args.command in commands:
        return commands[args.command](args)
    else:
        error(f"Unknown command: {args.command}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
