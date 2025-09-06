#!/usr/bin/env python3.11
"""
Build OpenCore ISO

This script builds an OpenCore ISO file from the current EFI configuration.
"""

import sys
import subprocess
import argparse
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import ROOT, log, warn, error, info, run_command, paths, validate_file_exists

def build_opencore_iso(force_rebuild=False):
    """Build the OpenCore ISO using the build script"""
    log("Building OpenCore ISO...")
    
    # Check if we need to clean first
    if force_rebuild:
        if paths.build_root.exists():
            log("Cleaning previous build...")
            run_command(f'rm -rf "{paths.build_root}"/*', check=False)
    
    # Ensure we have OpenCore assets
    ocvalidate_path = paths.opencore_root / "Utilities" / "ocvalidate" / "ocvalidate"
    if not ocvalidate_path.exists():
        error("OpenCore tools not found")
        error(f"Expected ocvalidate at: {ocvalidate_path}")
        error("Please run './ozzy fetch' first to download OpenCore assets")
        return False
    
    # Ensure EFI configuration exists
    if not paths.oc_efi.exists():
        error(f"OpenCore EFI configuration not found at: {paths.oc_efi}")
        error("Please apply a changeset first with: ./ozzy apply <changeset>")
        return False
    
    # Validate configuration before building
    validate_script = ROOT / 'scripts' / 'validate-config.py'
    if validate_script.exists():
        log("Validating OpenCore configuration before building...")
        if not run_command(f'python3.11 "{validate_script}"', "Validating configuration"):
            error("Configuration validation failed - not building ISO")
            return False
    else:
        warn("No validation script found, building without validation")
    
    # Set up the build directory structure that build_isos.sh expects
    build_efi_dir = paths.build_root / "efi"
    build_efi_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy our EFI directory to the build location
    log(f"Copying EFI from {paths.efi_build} to {build_efi_dir}")
    run_command(f'rsync -av --delete "{paths.efi_build}/" "{build_efi_dir}/"', "Copying EFI to build directory")
    
    # Run the build script
    build_script = ROOT / 'bin' / 'build_isos.sh'
    validate_file_exists(build_script, "Build script")
    
    # Make sure the script is executable
    run_command(f'chmod +x "{build_script}"')
    
    # Run the build script
    if not run_command(f'bash "{build_script}"', "Building OpenCore ISO"):
        return False
    
    # Check that ISO was created (build_isos.sh creates it in $OUT/opencore.iso)
    iso_path = ROOT / 'out' / 'opencore.iso'
    if iso_path.exists():
        log(f"OpenCore ISO created successfully: {iso_path}")
        return True
    else:
        error("ISO build completed but file not found")
        error(f"Expected ISO at: {iso_path}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Build OpenCore ISO')
    parser.add_argument('--force', '-f', action='store_true', help='Force rebuild (clean first)')
    parser.add_argument('--no-validate', action='store_true', help='Skip validation before building')
    
    args = parser.parse_args()
    
    try:
        if build_opencore_iso(force_rebuild=args.force):
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
