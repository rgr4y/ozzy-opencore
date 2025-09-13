#!/usr/bin/env python3.11
"""
Build OpenCore IMG

This script builds an OpenCore .img file from the current EFI configuration.
The .img file is deployable directly to Proxmox VMs as a disk image.
"""

import sys
import argparse
import subprocess
from pathlib import Path

# Import our common libraries and improved workflow
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import (
    ROOT, log, warn, error, info,
    validate_changeset_exists,
)
from lib.efi_builder import build_img_artifact


def build_opencore_img(changeset_name, force_rebuild=False, no_validate=False):
    """
    Build the OpenCore .img file using the improved workflow.
    The resulting .img will be a 50MB raw disk image with EFI partition.
    """
    log("Building OpenCore IMG...")

    # Validate changeset exists
    try:
        validate_changeset_exists(changeset_name)
    except FileNotFoundError:
        return False

    # Build via shared artifact function
    return build_img_artifact(changeset_name, force_rebuild=force_rebuild, no_validate=no_validate)


def build_img_file(*args, **kwargs):
    # Deprecated function retained to avoid import crashes if referenced elsewhere
    error("build_img_file is deprecated; use lib.efi_builder.build_img_artifact")
    return False


def main():
    parser = argparse.ArgumentParser(description='Build OpenCore IMG (disk image)')
    parser.add_argument('changeset', help='Changeset name (without .yaml)')
    parser.add_argument('--force', '-f', action='store_true', help='Force rebuild (clean first)')
    parser.add_argument('--no-validate', action='store_true', help='Skip validation before building')

    args = parser.parse_args()

    try:
        if build_opencore_img(changeset_name=args.changeset, force_rebuild=args.force, no_validate=args.no_validate):
            log("IMG build completed successfully!")
            return 0
        else:
            error("IMG build failed")
            return 1
    except KeyboardInterrupt:
        warn("Build cancelled by user")
        return 1
    except Exception as e:
        error(f"Build failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
