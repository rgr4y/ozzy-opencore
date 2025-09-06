#!/usr/bin/env python3

import sys
import argparse
from pathlib import Path
import yaml

# Import the SMBIOS generation functions
sys.path.append(str(Path(__file__).resolve().parent))
from generate_smbios import validate_and_generate_smbios, check_macserial_available

ROOT = Path(__file__).resolve().parents[1]

def generate_serial_for_changeset(changeset_name, force=False):
    """Generate SMBIOS serial numbers for a specific changeset"""
    
    changeset_file = ROOT / 'config' / 'changesets' / f'{changeset_name}.yaml'
    
    if not changeset_file.exists():
        print(f"[!] ERROR: Changeset file not found: {changeset_file}")
        return False
    
    print(f"[*] Processing changeset: {changeset_name}")
    print(f"[*] File: {changeset_file}")
    
    # Load changeset
    try:
        with open(changeset_file, 'r') as f:
            original_data = f.read()
            changeset_data = yaml.safe_load(original_data)
    except Exception as e:
        print(f"[!] ERROR: Could not load changeset file: {e}")
        return False
    
    if 'smbios' not in changeset_data:
        print("[!] ERROR: No SMBIOS configuration found in changeset")
        return False
    
    # Show current SMBIOS data
    smbios = changeset_data['smbios']
    print(f"[*] Current SMBIOS configuration:")
    print(f"    Model: {smbios.get('SystemProductName', 'Not set')}")
    print(f"    Serial: {smbios.get('SystemSerialNumber', 'Not set')}")
    print(f"    MLB: {smbios.get('MLB', 'Not set')}")
    print(f"    UUID: {smbios.get('SystemUUID', 'Not set')}")
    
    # Check if we need to generate (or if forced)
    if force:
        print("[*] Force flag set, generating new SMBIOS data...")
    
    # Check if macserial is available
    if not check_macserial_available():
        print("[!] ERROR: macserial utility not found")
        print("[!] Please run bin/fetch_assets.sh to download OpenCore utilities")
        return False
    
    # Create a backup
    backup_file = changeset_file.with_suffix('.yaml.backup')
    try:
        with open(backup_file, 'w') as f:
            f.write(original_data)
        print(f"[*] Backup created: {backup_file}")
    except Exception as e:
        print(f"[!] WARNING: Could not create backup: {e}")
    
    # Temporarily modify the force logic if needed
    if force:
        # Mark current values as placeholders to force regeneration
        smbios['SystemSerialNumber'] = 'PLACEHOLDER'
        smbios['MLB'] = 'PLACEHOLDER'
        smbios['SystemUUID'] = 'PLACEHOLDER'
    
    # Generate SMBIOS data
    success = validate_and_generate_smbios(changeset_data)
    
    if success:
        try:
            # Write back updated changeset with preserved formatting
            with open(changeset_file, 'w') as f:
                yaml.dump(changeset_data, f, default_flow_style=False, sort_keys=False, width=120)
            
            print(f"[✓] Changeset updated successfully!")
            print(f"[*] Updated SMBIOS configuration:")
            updated_smbios = changeset_data['smbios']
            print(f"    Model: {updated_smbios.get('SystemProductName', 'Not set')}")
            print(f"    Serial: {updated_smbios.get('SystemSerialNumber', 'Not set')}")
            print(f"    MLB: {updated_smbios.get('MLB', 'Not set')}")
            print(f"    UUID: {updated_smbios.get('SystemUUID', 'Not set')}")
            
            return True
        except Exception as e:
            print(f"[!] ERROR: Could not save updated changeset: {e}")
            # Restore from backup if possible
            try:
                with open(backup_file, 'r') as f:
                    with open(changeset_file, 'w') as out_f:
                        out_f.write(f.read())
                print(f"[*] Restored from backup due to save error")
            except:
                pass
            return False
    else:
        print("[!] SMBIOS generation failed")
        return False

def list_available_changesets():
    """List all available changesets"""
    changesets_dir = ROOT / 'config' / 'changesets'
    
    if not changesets_dir.exists():
        print("[!] No changesets directory found")
        return []
    
    changesets = []
    for yaml_file in changesets_dir.glob('*.yaml'):
        changeset_name = yaml_file.stem
        changesets.append(changeset_name)
    
    return sorted(changesets)

def main():
    parser = argparse.ArgumentParser(
        description='Generate SMBIOS serial numbers and UUIDs for OpenCore changesets',
        epilog='''
Examples:
  # Generate SMBIOS for a specific changeset (only if placeholders detected)
  python3 scripts/generate_serial.py --changeset ryzen3950x_rx580_mac
  
  # Force generation of new SMBIOS data
  python3 scripts/generate_serial.py --changeset ryzen3950x_rx580_mac --force
  
  # List available changesets
  python3 scripts/generate_serial.py --list
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument('--changeset', '-c', 
                       help='Name of the changeset to generate SMBIOS for')
    parser.add_argument('--force', '-f', action='store_true',
                       help='Force generation of new SMBIOS data even if current values are not placeholders')
    parser.add_argument('--list', '-l', action='store_true',
                       help='List all available changesets')
    
    args = parser.parse_args()
    
    if args.list:
        print("[*] Available changesets:")
        changesets = list_available_changesets()
        if changesets:
            for changeset in changesets:
                print(f"    {changeset}")
        else:
            print("    No changesets found")
        return
    
    if not args.changeset:
        print("[!] ERROR: Please specify a changeset with --changeset or use --list to see available changesets")
        parser.print_help()
        sys.exit(1)
    
    try:
        success = generate_serial_for_changeset(args.changeset, force=args.force)
        if not success:
            sys.exit(1)
    except KeyboardInterrupt:
        print("\n[!] Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n[!] Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
