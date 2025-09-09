#!/usr/bin/env python3.11
"""
SMBIOS generation script for OpenCore changesets.

This script provides comprehensive SMBIOS data generation and validation,
including serial numbers, MLB, UUIDs, and ROM addresses for OpenCore changesets.
It automatically detects placeholder values and generates proper replacements.
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
    validate_and_generate_smbios, validate_and_generate_serial_mlb_only, 
    validate_and_generate_rom_uuid_only, get_smbios_info,
    check_macserial_available, validate_changeset_exists
)

def generate_smbios_for_changeset(changeset_name, force=False, serial_only=False, rom_uuid_only=False):
    """Generate SMBIOS data for a specific changeset"""
    
    log(f"Processing changeset: {changeset_name}")
    
    # Load changeset
    changeset_data = load_changeset(changeset_name)
    if not changeset_data:
        return False
    
    from lib.smbios import get_smbios_section
    smbios, section_path = get_smbios_section(changeset_data)
    
    if not smbios:
        error("No PlatformInfo.Generic or SMBIOS configuration found in changeset")
        return False
    
    log(f"Using {section_path} for SMBIOS data")
    
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
    
    if serial_only:
        log("Serial-only mode: preserving existing UUID and ROM...")
    
    if rom_uuid_only:
        log("ROM/UUID-only mode: preserving existing serial and MLB...")
    
    # Check if macserial is available
    if not check_macserial_available():
        error("macserial utility not available")
        error("Please run './ozzy fetch' first to download OpenCore tools")
        return False
    
    # Generate SMBIOS data using appropriate function
    success = False
    if serial_only:
        success = validate_and_generate_serial_mlb_only(changeset_data, force)
    elif rom_uuid_only:
        success = validate_and_generate_rom_uuid_only(changeset_data, force)
    else:
        success = validate_and_generate_smbios(changeset_data, force)
    
    if success:
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

def list_changesets_with_serials():
    """List all changesets with their current SMBIOS serial numbers"""
    changesets = list_available_changesets()
    if not changesets:
        warn("No changesets found")
        return
    
    log("Available changesets with serial numbers:")
    for changeset in changesets:
        try:
            changeset_data = load_changeset(changeset)
            if changeset_data:
                from lib.smbios import get_smbios_section
                smbios, section_path = get_smbios_section(changeset_data)
                
                if smbios:
                    smbios_info = get_smbios_info(changeset_data)
                    serial = smbios_info['serial']
                    model = smbios_info['model']
                    # Show if it's a placeholder
                    placeholder_note = " (placeholder)" if serial in ["PLACEHOLDER", ""] else ""
                    info(f"- {changeset:<25} {model:<12} {serial}{placeholder_note}")
                else:
                    info(f"- {changeset:<25} {'N/A':<12} No PlatformInfo.Generic or SMBIOS data")
            else:
                info(f"- {changeset:<25} {'ERROR':<12} Failed to load changeset")
        except Exception as e:
            info(f"- {changeset:<25} {'ERROR':<12} Failed to load: {e}")

def generate_smbios_only():
    """Generate SMBIOS data without saving to any changeset"""
    log("Generating SMBIOS data (not saving to changeset)...")
    
    # Check if macserial is available
    if not check_macserial_available():
        error("macserial utility not available")
        error("Please run './ozzy fetch' first to download OpenCore tools")
        return False
    
    # Create a temporary changeset structure with default iMacPro1,1
    temp_changeset = {
        'smbios': {
            'SystemProductName': 'iMacPro1,1',
            'SystemSerialNumber': 'PLACEHOLDER',
            'MLB': 'PLACEHOLDER', 
            'SystemUUID': 'PLACEHOLDER',
            'ROM': 'PLACEHOLDER'
        }
    }
    
    # Generate SMBIOS data (force=True to always generate)
    if validate_and_generate_smbios(temp_changeset, force=True):
        # Show the generated SMBIOS data
        smbios_info = get_smbios_info(temp_changeset)
        log("Generated SMBIOS data:")
        info(f"Model: {smbios_info['model']}")
        info(f"Serial: {smbios_info['serial']}")
        info(f"MLB: {smbios_info['mlb']}")
        info(f"UUID: {smbios_info['uuid']}")
        info(f"ROM: {smbios_info['rom']}")
        log("Note: This data was not saved to any changeset")
        return True
    else:
        error("Failed to generate SMBIOS data")
        return False

def main():
    parser = argparse.ArgumentParser(
        description='Generate SMBIOS data (serial numbers, MLB, UUIDs, ROM) for OpenCore changesets',
        epilog='''
Examples:
  # Generate SMBIOS for a changeset (only if placeholders detected)
  python3.11 scripts/generate-serial.py ryzen3950x_rx580_mac

  # Force generation of new SMBIOS data
  python3.11 scripts/generate-serial.py ryzen3950x_rx580_mac --force

  # Only regenerate serial and MLB, preserve UUID and ROM
  python3.11 scripts/generate-serial.py ryzen3950x_rx580_mac --serial-only

  # Only regenerate ROM and UUID, preserve serial and MLB
  python3.11 scripts/generate-serial.py ryzen3950x_rx580_mac --rom-uuid-only

  # Force regenerate only serial and MLB
  python3.11 scripts/generate-serial.py ryzen3950x_rx580_mac --force --serial-only

  # List available changesets with their serial numbers
  python3.11 scripts/generate-serial.py --list

  # Generate SMBIOS data without saving to any changeset
  python3.11 scripts/generate-serial.py --generate-only
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('changeset', nargs='?',
                       help='Name of the changeset to generate SMBIOS data for')
    parser.add_argument('--force', '-f', action='store_true',
                       help='Force generation of new SMBIOS data even if current values are not placeholders')
    parser.add_argument('--list', '-l', action='store_true',
                       help='List available changesets with their serial numbers')
    parser.add_argument('--generate-only', '-g', action='store_true',
                       help='Generate SMBIOS data without saving to any changeset')
    parser.add_argument('--serial-only', '-s', action='store_true',
                       help='Only regenerate serial and MLB, preserve existing UUID and ROM')
    parser.add_argument('--rom-uuid-only', '-r', action='store_true',
                       help='Only regenerate ROM and UUID, preserve existing serial and MLB')
    
    args = parser.parse_args()
    
    if args.list:
        list_changesets_with_serials()
        return 0
    
    if args.generate_only:
        if generate_smbios_only():
            return 0
        else:
            return 1
    
    if not args.changeset:
        error("Changeset name is required (provide changeset argument or use --list)")
        parser.print_help()
        return 1
    
    # Remove .yaml extension if provided
    changeset_name = args.changeset
    if changeset_name.endswith('.yaml'):
        changeset_name = changeset_name[:-5]
    
    # Validate changeset exists (this will show recent changesets if not found)
    validate_changeset_exists(changeset_name)
    
    # Check for conflicting options
    if args.serial_only and args.rom_uuid_only:
        error("Cannot use --serial-only and --rom-uuid-only together")
        return 1
    
    if generate_smbios_for_changeset(changeset_name, args.force, args.serial_only, args.rom_uuid_only):
        return 0
    else:
        return 1

if __name__ == "__main__":
    sys.exit(main())
