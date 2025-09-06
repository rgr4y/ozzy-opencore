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
    run_command, validate_file_exists,
    get_project_paths, ensure_directory, cleanup_macos_metadata,
    build_complete_efi_structure, copy_efi_for_build, validate_changeset_exists
)


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

    # Get project paths
    paths = get_project_paths()

    # Clean previous build if requested
    if force_rebuild and paths['build_root'].exists():
        log("Cleaning previous build...")
        run_command(f'rm -rf "{paths["build_root"]}"/*', check=False)

    # Validate OpenCore assets
    ocvalidate_path = paths['opencore'] / "Utilities" / "ocvalidate" / "ocvalidate"
    if not ocvalidate_path.exists():
        error("OpenCore tools not found")
        error(f"Expected ocvalidate at: {ocvalidate_path}")
        error("Please run './ozzy fetch' first to download OpenCore assets")
        return False

    # Build complete EFI structure
    if not build_complete_efi_structure(changeset_name=changeset_name, force_rebuild=force_rebuild):
        error("Failed to build complete EFI structure")
        return False

    # Validate EFI structure
    source_efi = paths['out'] / 'build' / 'efi' / 'EFI'
    if not source_efi.exists():
        error(f"Source EFI structure not found: {source_efi}")
        return False

    # Optionally validate configuration
    if not no_validate:
        validate_script = paths['scripts'] / 'validate-config.py'
        if validate_script.exists():
            log("Validating OpenCore configuration before building...")
            if not run_command(f'python3.11 "{validate_script}"', "Validating configuration"):
                error("Configuration validation failed - not building ISO")
                return False
        else:
            warn("No validation script found, building without validation")

    # The EFI structure is already built in the correct location for the ISO builder
    # (/out/build/efi/EFI/) so no additional copying is needed

    # Run the build script (creates EFI bootable ISO via El Torito)
    build_script = paths['bin'] / 'build_isos.sh'
    validate_file_exists(build_script, "Build script")
    run_command(f'chmod +x "{build_script}"')
    if not run_command(f'bash "{build_script}"', "Building OpenCore ISO"):
        error("ISO build script failed")
        return False

    # Check that ISO was created
    iso_path = paths['out'] / 'opencore.iso'
    if iso_path.exists():
        log(f"OpenCore ISO created successfully: {iso_path}")
        info("The ISO is EFI bootable (El Torito) as created by build_isos.sh.")

        # Debug: Mount ISO and show its contents
        import tempfile
        import subprocess
        mount_point = None
        try:
            # Create a temp mount point
            with tempfile.TemporaryDirectory() as tmpdir:
                mount_point = tmpdir
                log(f"Mounting ISO for inspection at {mount_point}...")
                # Attach ISO
                attach_cmd = ["hdiutil", "attach", str(iso_path), "-mountpoint", mount_point, "-nobrowse"]
                result = subprocess.run(attach_cmd, capture_output=True, text=True)
                if result.returncode == 0:
                    log("Mounted ISO. Showing contents:")
                    tree_cmd = ["tree", mount_point]
                    tree_result = subprocess.run(tree_cmd, capture_output=True, text=True)
                    print(tree_result.stdout)
                else:
                    warn(f"Failed to mount ISO: {result.stderr}")
                # Detach ISO
                subprocess.run(["hdiutil", "detach", mount_point])
        except Exception as e:
            warn(f"Could not inspect ISO contents: {e}")

        return True
    else:
        error("ISO build completed but file not found")
        error(f"Expected ISO at: {iso_path}")
        return False


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
