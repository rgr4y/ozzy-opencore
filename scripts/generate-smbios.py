#!/usr/bin/env python3.11
"""
Refactored generate_smbios.py using common libraries.

This script handles SMBIOS data generation and validation for OpenCore changesets.
"""

import sys
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import (
    log, warn, error,
    validate_and_generate_smbios,
    load_changeset, save_changeset,
    get_changeset_path
)

def main():
    if len(sys.argv) != 2:
        print("Usage: generate_smbios.py <changeset_name>")
        sys.exit(1)
    
    changeset_name = sys.argv[1]
    changeset_file = get_changeset_path(changeset_name)
    
    if not changeset_file.exists():
        error(f"Changeset file not found: {changeset_file}")
        sys.exit(1)
    
    # Load changeset using our library
    changeset_data = load_changeset(changeset_name)
    if not changeset_data:
        sys.exit(1)
    
    # Validate and generate SMBIOS
    if validate_and_generate_smbios(changeset_data):
        # Save the updated changeset
        if save_changeset(changeset_name, changeset_data):
            log("SMBIOS data generated and saved successfully")
        else:
            error("Failed to save updated changeset")
            sys.exit(1)
    else:
        error("Failed to generate SMBIOS data")
        sys.exit(1)

if __name__ == "__main__":
    main()
