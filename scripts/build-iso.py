#!/usr/bin/env python3.11
"""
Build OpenCore ISO

This script builds an OpenCore ISO file from the current EFI configuration.
"""


import sys
import argparse
import subprocess
from pathlib import Path

# Import our common libraries and improved workflow
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import (
    ROOT, log, warn, error, info,
    validate_file_exists,
    validate_changeset_exists,
    paths as pm,
)
from lib.efi_builder import build_iso_artifact


def build_opencore_iso(changeset_name, force_rebuild=False, no_validate=False):
    """
    Build the OpenCore ISO using the improved workflow.
    The resulting ISO will be EFI bootable (El Torito), as handled by build_isos.sh.
    """
    log("Building OpenCore ISO...")
    # Validate changeset exists
    try:
        validate_changeset_exists(changeset_name)
    except FileNotFoundError:
        return False
    return build_iso_artifact(changeset_name, force_rebuild=force_rebuild, no_validate=no_validate)


def main():
    parser = argparse.ArgumentParser(description='Build OpenCore ISO (EFI bootable)')
    parser.add_argument('changeset', help='Changeset name (without .yaml)')
    parser.add_argument('--force', '-f', action='store_true', help='Force rebuild (clean first)')
    parser.add_argument('--no-validate', action='store_true', help='Skip validation before building')

    args = parser.parse_args()

    try:
        if build_opencore_iso(changeset_name=args.changeset, force_rebuild=args.force, no_validate=args.no_validate):
            log("ISO build completed successfully!")
            return 0
        else:
            error("ISO build failed")
            return 1
    except KeyboardInterrupt:
        warn("Build cancelled by user")
        return 1
    except Exception as e:
        error(f"Build failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
