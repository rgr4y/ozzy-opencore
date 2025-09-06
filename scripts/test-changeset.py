#!/usr/bin/env python3.11

import os
import sys
import yaml
from pathlib import Path

# Add parent directory to path to import deploy
# TODO: Refactor to use lib paths
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

ROOT = Path(__file__).resolve().parents[1]

def test_changeset_parsing():
    """Test that the changeset is being parsed correctly"""
    changeset_file = ROOT / 'config' / 'changesets' / 'ryzen3950x_rx580_mac.yaml'
    
    print(f"[*] Testing changeset parsing: {changeset_file}")
    
    if not changeset_file.exists():
        print(f"[!] ERROR: Changeset file not found")
        return False
    
    with open(changeset_file, 'r') as f:
        changeset_data = yaml.safe_load(f)
    
    print(f"[*] Changeset loaded successfully")
    
    if 'proxmox_vm' not in changeset_data:
        print(f"[!] ERROR: No proxmox_vm section found")
        return False
    
    proxmox_config = changeset_data['proxmox_vm']
    print(f"[*] Found proxmox_vm section")
    
    if 'assets' in proxmox_config:
        print(f"[*] Found {len(proxmox_config['assets'])} assets:")
        for asset in proxmox_config['assets']:
            src_relative = asset['src']
            dest_path = asset['dest']
            
            # Handle relative paths properly
            if src_relative.startswith('./'):
                src_path = ROOT / src_relative[2:]  # Remove "./" prefix
            else:
                src_path = ROOT / src_relative
            
            print(f"  - {src_relative} -> {dest_path}")
            print(f"    Resolved path: {src_path}")
            print(f"    Exists: {src_path.exists()}")
            if src_path.exists():
                print(f"    Size: {src_path.stat().st_size} bytes")
    
    if 'conf_overrides' in proxmox_config:
        print(f"[*] Found {len(proxmox_config['conf_overrides'])} configuration overrides:")
        for key, value in proxmox_config['conf_overrides'].items():
            print(f"  - {key} = {value}")
            if key == 'hostpci0':
                print(f"    ^^ This should contain romfile=/usr/share/kvm/RX580.rom")
    
    return True

if __name__ == "__main__":
    if test_changeset_parsing():
        print("[✓] Changeset parsing test passed")
    else:
        print("[✗] Changeset parsing test failed")
        sys.exit(1)
