#!/usr/bin/env python3.11
"""
Refactored generate-serial.py using common libraries.

This script provides a command-line interface for generating SMBIOS serial numbers
and UUIDs for OpenCore changesets.
"""

import sys
import argparse
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import (
    ROOT, log, warn, error, info,
    list_available_changesets,
    load_changeset, save_changeset,
    validate_and_generate_smbios, get_smbios_info,
    check_macserial_available
)

def generate_serial_for_changeset(changeset_name, force=False):
    """Generate SMBIOS serial numbers for a specific changeset"""
    
    log(f"Processing changeset: {changeset_name}")
    
    # Load changeset
    changeset_data = load_changeset(changeset_name)
    if not changeset_data:
        return False
    
    if 'smbios' not in changeset_data:
        error("No SMBIOS configuration found in changeset")
        return False
    
    # Show current SMBIOS data
    smbios_info = get_smbios_info(changeset_data)
    log("Current SMBIOS configuration:")
    info(f"Model: {smbios_info['model']}")
    info(f"Serial: {smbios_info['serial']}")
    info(f"MLB: {smbios_info['mlb']}")
    info(f"UUID: {smbios_info['uuid']}")
    info(f"ROM: {smbios_info['rom']}")
    
    # Check if we need to generate (or if forced)
    if force:
        log("Force flag set, generating new SMBIOS data...")
    
    # Check if macserial is available
    if not check_macserial_available():
        error("macserial utility not available")
        error("Please run './ozzy fetch' first to download OpenCore tools")
        return False
    
    # Generate SMBIOS data
    if validate_and_generate_smbios(changeset_data, force):
        # Save updated changeset
        if save_changeset(changeset_name, changeset_data):
            log("SMBIOS data updated successfully")
            
            # Show new SMBIOS data
            new_smbios_info = get_smbios_info(changeset_data)
            log("New SMBIOS configuration:")
            info(f"Model: {new_smbios_info['model']}")
            info(f"Serial: {new_smbios_info['serial']}")
            info(f"MLB: {new_smbios_info['mlb']}")
            info(f"UUID: {new_smbios_info['uuid']}")
            info(f"ROM: {new_smbios_info['rom']}")
            
            return True
        else:
            error("Failed to save updated changeset")
            return False
    else:
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Generate SMBIOS serial numbers and UUIDs for OpenCore changesets',
        epilog='''
Examples:
  # Generate SMBIOS for a specific changeset (only if placeholders detected)
  python3.11 scripts/generate-serial.py ryzen3950x_rx580_mac

  # Force generation of new SMBIOS data
  python3.11 scripts/generate-serial.py ryzen3950x_rx580_mac --force

  # List available changesets
  python3.11 scripts/generate-serial.py --list
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('changeset', nargs='?',
                       help='Name of the changeset to generate SMBIOS for')
    parser.add_argument('--force', '-f', action='store_true',
                       help='Force generation of new SMBIOS data even if current values are not placeholders')
    parser.add_argument('--list', '-l', action='store_true',
                       help='List available changesets')
    
    args = parser.parse_args()
    
    if args.list:
        changesets = list_available_changesets()
        if changesets:
            log("Available changesets:")
            for changeset in changesets:
                info(f"- {changeset}")
        else:
            warn("No changesets found")
        return 0
    
    if not args.changeset:
        error("Changeset name is required (provide changeset argument or use --list)")
        parser.print_help()
        return 1
    
    # Remove .yaml extension if provided
    changeset_name = args.changeset
    if changeset_name.endswith('.yaml'):
        changeset_name = changeset_name[:-5]
    
    if generate_serial_for_changeset(changeset_name, args.force):
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
