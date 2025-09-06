#!/usr/bin/env python3
"""
Refactored apply_changeset.py using common libraries.

This script applies OpenCore configuration changesets by merging them with
the base OpenCore configuration template.
"""

import sys
import argparse
import yaml
import json
import subprocess
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).parent.parent / 'lib'))
from lib import (
    ROOT, log, warn, error,
    convert_data_values, CustomJSONEncoder,
    validate_file_exists
)

# Project-specific paths
EFI = ROOT / "efi-build" / "EFI" / "OC"
TEMPLATE = ROOT / "out" / "opencore" / "Docs" / "Sample.plist"
PATCHER = ROOT / "scripts" / "patch_plist.py"

def main():
    parser = argparse.ArgumentParser(
        description='Apply OpenCore configuration changeset',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("changeset", help="Path to changeset YAML file")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without applying them")
    
    args = parser.parse_args()
    
    # Validate inputs
    changeset_path = Path(args.changeset)
    validate_file_exists(changeset_path, "Changeset file")
    validate_file_exists(TEMPLATE, "OpenCore template")
    validate_file_exists(PATCHER, "Plist patcher script")
    
    # Load changeset
    log(f"Loading changeset: {changeset_path}")
    try:
        with open(changeset_path, 'r') as f:
            changeset_data = yaml.safe_load(f)
    except Exception as e:
        error(f"Failed to load changeset: {e}")
        return 1
    
    # Convert data types for plist handling
    log("Converting data types for plist compatibility")
    converted_data = convert_data_values(changeset_data)
    
    # Prepare JSON data for patcher
    try:
        json_data = json.dumps(converted_data, cls=CustomJSONEncoder, indent=2)
    except Exception as e:
        error(f"Failed to serialize changeset data: {e}")
        return 1
    
    if args.dry_run:
        log("DRY RUN MODE - Changes will not be applied")
        print("Changeset data that would be applied:")
        print(json_data)
        return 0
    
    # Ensure output directory exists
    EFI.mkdir(parents=True, exist_ok=True)
    
    # Apply changeset using patcher
    log("Applying changeset to OpenCore configuration")
    try:
        cmd = [
            sys.executable, str(PATCHER),
            str(TEMPLATE),
            str(EFI / "config.plist")
        ]
        
        process = subprocess.Popen(
            cmd, 
            stdin=subprocess.PIPE, 
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=ROOT
        )
        
        stdout, stderr = process.communicate(input=json_data)
        
        if process.returncode != 0:
            error(f"Patcher failed with exit code {process.returncode}")
            if stderr:
                error(f"Error output: {stderr}")
            return 1
        
        if stdout:
            log(f"Patcher output: {stdout}")
            
    except Exception as e:
        error(f"Failed to run patcher: {e}")
        return 1
    
    log(f"Successfully applied changeset to {EFI / 'config.plist'}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
