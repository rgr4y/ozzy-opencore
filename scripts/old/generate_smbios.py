#!/usr/bin/env python3.11

import subprocess
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def check_macserial_available():
    """Check if macserial utility is available"""
    macserial_path = ROOT / "out" / "opencore" / "Utilities" / "macserial" / "macserial"
    return macserial_path.exists()

def generate_smbios_data(model="iMacPro1,1"):
    """Generate SMBIOS data using macserial utility"""
    macserial_path = ROOT / "out" / "opencore" / "Utilities" / "macserial" / "macserial"
    
    if not macserial_path.exists():
        raise FileNotFoundError(f"macserial not found at {macserial_path}")
    
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

def generate_uuid():
    """Generate a random UUID"""
    import uuid
    return str(uuid.uuid4()).upper()

def is_placeholder_serial(serial):
    """Check if serial number is a placeholder"""
    placeholders = [
        "C02XD1WJHX87",  # iMacPro1,1 placeholder
        "F5KFV03CP7QM",  # MacPro7,1 placeholder
        "PLACEHOLDER",
        "CHANGEME",
        "XXXX"
    ]
    return any(placeholder in serial for placeholder in placeholders)

def is_placeholder_mlb(mlb):
    """Check if MLB is a placeholder"""
    placeholders = [
        "C02309XXXXHX87XX",
        "F5K124100J9K3F7JA", 
        "PLACEHOLDER",
        "CHANGEME",
        "XXXX"
    ]
    return any(placeholder in mlb for placeholder in placeholders)

def is_placeholder_uuid(uuid_str):
    """Check if UUID is a placeholder"""
    placeholders = [
        "12345678-1234-1234-1234-123456789ABC",
        "CE35AC97-8B7E-452A-A2AB-A5907F81DA12",
        "PLACEHOLDER"
    ]
    return any(placeholder in uuid_str for placeholder in placeholders)

def validate_and_generate_smbios(changeset_data):
    """Validate SMBIOS data and generate if needed"""
    
    if 'smbios' not in changeset_data:
        print("[!] No SMBIOS configuration found in changeset")
        return False
    
    smbios = changeset_data['smbios']
    model = smbios.get('SystemProductName', 'iMacPro1,1')
    serial = smbios.get('SystemSerialNumber', '')
    mlb = smbios.get('MLB', '')
    uuid_str = smbios.get('SystemUUID', '')
    
    needs_generation = False
    
    # Check if we need to generate new SMBIOS data
    if is_placeholder_serial(serial):
        print(f"[*] Placeholder serial detected: {serial}")
        needs_generation = True
    
    if is_placeholder_mlb(mlb):
        print(f"[*] Placeholder MLB detected: {mlb}")
        needs_generation = True
    
    if is_placeholder_uuid(uuid_str):
        print(f"[*] Placeholder UUID detected: {uuid_str}")
        needs_generation = True
    
    if needs_generation:
        print(f"[*] Generating new SMBIOS data for {model}...")
        
        # Check if macserial is available
        if not check_macserial_available():
            print("[!] ERROR: macserial utility not found")
            print("[!] Please run scripts/fetch-assets.py to download OpenCore utilities")
            return False
        
        try:
            # Generate new serial and MLB
            new_serial, new_mlb = generate_smbios_data(model)
            new_uuid = generate_uuid()
            
            print(f"[✓] Generated SMBIOS data:")
            print(f"    Model: {model}")
            print(f"    Serial: {new_serial}")
            print(f"    MLB: {new_mlb}")
            print(f"    UUID: {new_uuid}")
            
            # Update changeset data
            smbios['SystemSerialNumber'] = new_serial
            smbios['MLB'] = new_mlb
            smbios['SystemUUID'] = new_uuid
            
            return True
            
        except Exception as e:
            print(f"[!] ERROR generating SMBIOS data: {e}")
            return False
    else:
        print("[✓] SMBIOS data appears to be real (not placeholder)")
        return True

if __name__ == "__main__":
    import yaml
    
    if len(sys.argv) != 2:
        print("Usage: generate_smbios.py <changeset_file>")
        sys.exit(1)
    
    changeset_file = Path(sys.argv[1])
    
    if not changeset_file.exists():
        print(f"[!] Changeset file not found: {changeset_file}")
        sys.exit(1)
    
    # Load changeset
    with open(changeset_file, 'r') as f:
        changeset_data = yaml.safe_load(f)
    
    # Validate and generate SMBIOS
    if validate_and_generate_smbios(changeset_data):
        # Write back updated changeset
        with open(changeset_file, 'w') as f:
            yaml.dump(changeset_data, f, default_flow_style=False, sort_keys=False)
        print(f"[✓] Changeset updated: {changeset_file}")
    else:
        print("[!] SMBIOS validation/generation failed")
        sys.exit(1)
