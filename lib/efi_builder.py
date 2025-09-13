#!/usr/bin/env python3.11
"""
EFI Builder Library

Common functions for building complete OpenCore EFI structures and packaging
artifacts. Ensures all components (ACPI, Drivers, Tools, Kexts, etc.) are
properly included.
"""

import shutil
import subprocess
import yaml
import zipfile
import tempfile
from pathlib import Path
import hashlib
import json
import yaml
from . import ROOT, log, warn, error, info, run_command, ensure_directory, cleanup_macos_metadata
from .paths import paths as pm

def _load_changeset_yaml(changeset_name: str):
    """Load changeset YAML as a Python dict or return None on error."""
    cs_path = pm.changesets / f"{changeset_name}.yaml"
    try:
        with open(cs_path, 'r') as f:
            return yaml.safe_load(f)
    except Exception as e:
        error(f"Failed to load changeset: {e}")
        return None


def _canonical_asset_requirements(changeset_data: dict) -> dict:
    """Extract a canonical representation of required assets from changeset.

    Includes Kexts/KernelAdd, UefiDrivers, and AcpiAdd lists normalized and sorted.
    """
    def _norm_list(x):
        return sorted(list({str(i).strip() for i in x}))

    req = {
        'kexts': [],
        'drivers': [],
        'acpi': [],
    }
    if not isinstance(changeset_data, dict):
        return req

    # Kexts
    kexts = (
        changeset_data.get('Kexts')
        or changeset_data.get('kexts')
        or changeset_data.get('KernelAdd')
        or changeset_data.get('kernel_add')
        or []
    )
    for k in kexts or []:
        if isinstance(k, dict):
            bundle = k.get('bundle') or k.get('BundlePath') or ''
            if bundle:
                req['kexts'].append(bundle)

    # UEFI Drivers
    drivers = changeset_data.get('UefiDrivers') or []
    for d in drivers or []:
        if isinstance(d, dict):
            path = d.get('path') or d.get('Path') or ''
            if path:
                req['drivers'].append(path)

    # ACPI
    acpi = changeset_data.get('AcpiAdd') or changeset_data.get('acpi_add') or []
    for a in acpi or []:
        # can be a string or dict depending on producer
        if isinstance(a, str):
            req['acpi'].append(a)
        elif isinstance(a, dict):
            # Some formats use a dict with Path
            p = a.get('Path') or a.get('path')
            if p:
                req['acpi'].append(p)

    # Deduplicate and sort
    req['kexts'] = _norm_list(req['kexts'])
    req['drivers'] = _norm_list(req['drivers'])
    req['acpi'] = _norm_list(req['acpi'])
    return req


def _hash_requirements(req: dict) -> str:
    data = json.dumps(req, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


def _requirements_hash_path(changeset_name: str) -> Path:
    pm.build_root.mkdir(parents=True, exist_ok=True)
    return pm.build_root / f"{changeset_name}.assets.sha256"


def _ensure_assets_fresh_for_changeset(changeset_name: str) -> bool:
    """Ensure assets are up-to-date for the changeset's requirements.

    Computes a hash of kexts/drivers/ACPI requirements. If it differs from the
    last stored hash, runs fetch-assets and updates the hash. Also triggers
    fetch if kexts are missing.
    """
    cs = _load_changeset_yaml(changeset_name)
    if not cs:
        return False
    req = _canonical_asset_requirements(cs)
    new_hash = _hash_requirements(req)
    hash_file = _requirements_hash_path(changeset_name)
    old_hash = None
    try:
        if hash_file.exists():
            old_hash = hash_file.read_text().strip()
    except Exception:
        old_hash = None

    # Also check if kexts directory is empty/missing
    kexts_dir = (pm.efi_build / 'EFI' / 'OC' / 'Kexts')
    kexts_missing = not kexts_dir.exists() or not any(kexts_dir.glob('*.kext'))

    if (old_hash != new_hash) or kexts_missing:
        if old_hash != new_hash:
            info("Asset requirements changed; running fetch to update assets")
        else:
            info("Kexts directory missing or empty; running fetch to download assets")
        fetch_script = pm.scripts / 'fetch-assets.py'
        if not run_command(f'python3.11 "{fetch_script}"', "Fetching assets"):
            error("Failed to fetch assets")
            return False
        try:
            hash_file.write_text(new_hash)
        except Exception:
            pass
    return True


def manage_changeset_kexts(changeset_name, target_efi_dir):
    """
    Prune kexts in the EFI structure to only include those specified in the changeset.
    
    Args:
        changeset_name: Name of the changeset
        target_efi_dir: Target EFI directory (typically out/build/efi/EFI)
        
    Returns:
        bool: True if successful, False otherwise
    """
    changeset_path = pm.changesets / f"{changeset_name}.yaml"
    
    if not changeset_path.exists():
        error(f"Changeset file not found: {changeset_path}")
        return False
    
    # Load changeset to get kext specifications
    changeset_data = _load_changeset_yaml(changeset_name)
    if not changeset_data:
        return False
    
    if 'Kexts' not in changeset_data:
        log("No kexts specified in changeset")
        return True
    
    # Get the kexts directory
    kexts_dir = target_efi_dir / 'OC' / 'Kexts'
    if not kexts_dir.exists():
        error(f"Kexts directory not found: {kexts_dir}")
        return False
    
    # Get list of kexts specified in changeset
    changeset_kexts = set()
    for kext_info in changeset_data['Kexts']:
        changeset_kexts.add(kext_info['bundle'])
    
    log(f"Changeset specifies {len(changeset_kexts)} kexts")
    
    # Remove kexts not in changeset
    removed_count = 0
    for kext_item in kexts_dir.iterdir():
        if kext_item.is_dir() and kext_item.name.endswith('.kext'):
            if kext_item.name not in changeset_kexts:
                log(f"Removing unused kext: {kext_item.name}")
                shutil.rmtree(kext_item)
                removed_count += 1
            else:
                log(f"✓ Keeping changeset kext: {kext_item.name}")
    
    # Verify all changeset kexts are present
    missing_kexts = []
    for kext_name in changeset_kexts:
        kext_path = kexts_dir / kext_name
        if not kext_path.exists():
            missing_kexts.append(kext_name)
    
    if missing_kexts:
        error(f"Missing required kexts: {', '.join(missing_kexts)}")
        return False
    
    log(f"✓ Kext management complete: removed {removed_count}, kept {len(changeset_kexts)}")
    return True

def manage_changeset_drivers(changeset_name, target_efi_dir):
    """
    Copy drivers specified in changeset to the EFI Drivers directory.
    
    Args:
        changeset_name: Name of the changeset
        target_efi_dir: Target EFI directory containing OC subfolder
        
    Returns:
        bool: True if successful, False otherwise
    """
    from . import log, warn, error
    from .changeset import load_changeset
    import shutil
    
    # Load changeset
    changeset_data = load_changeset(changeset_name)
    if not changeset_data:
        error(f"Failed to load changeset: {changeset_name}")
        return False
    
    # Get the drivers directory
    drivers_dir = target_efi_dir / 'OC' / 'Drivers'
    drivers_dir.mkdir(parents=True, exist_ok=True)
    
    # Copy drivers specified in changeset
    if 'UefiDrivers' in changeset_data:
        log(f"Copying drivers specified in changeset...")
        copied_count = 0
        
        for driver in changeset_data['UefiDrivers']:
            driver_name = driver['path']
            
            # Skip if already exists (e.g. essential drivers)
            target_driver = drivers_dir / driver_name
            if target_driver.exists():
                log(f"Driver already exists: {driver_name}")
                continue
            
            # Look for drivers in various locations
            source_locations = [
                ROOT / "out" / "opencore" / "X64" / "EFI" / "OC" / "Drivers" / driver_name,
                ROOT / "out" / "ocbinarydata-repo" / "Drivers" / driver_name,
                ROOT / "out" / "opencore" / "Drivers" / driver_name,
                ROOT / "assets" / "drivers" / driver_name,
            ]
            
            source_driver = None
            for location in source_locations:
                if location.exists():
                    source_driver = location
                    break
            
            if source_driver:
                shutil.copy2(source_driver, target_driver)
                log(f"Copied driver: {driver_name}")
                copied_count += 1
            else:
                warn(f"Driver not found: {driver_name} (searched in {len(source_locations)} locations)")
        
        log(f"Driver management completed: {copied_count} drivers copied")
    
    return True

def build_complete_efi_structure(changeset_name, force_rebuild=False, apply_changeset: bool = True):
    """
    Build a complete EFI structure with OpenCore, kexts, drivers, and applied changeset.
    This is the unified function used by both USB and ISO builders.
    
    Args:
        changeset_name: Name of the changeset to apply
        force_rebuild: Whether to force a complete rebuild
        
    Returns:
        bool: True if successful, False otherwise
    """
    from .common import get_project_paths, log, error, run_command
    import subprocess
    import sys
    
    target_dir = pm.efi_build / 'EFI'
    
    log(f"Building complete EFI structure in: {target_dir.parent}")
    
    # Ensure assets are fresh for this changeset or force fetch on rebuild
    if force_rebuild:
        info("Force rebuild requested; updating assets via fetch...")
        fetch_script = pm.scripts / 'fetch-assets.py'
        if not run_command(f'python3.11 "{fetch_script}"', "Fetching assets"):
            error("Failed to fetch assets")
            return False
    else:
        if not _ensure_assets_fresh_for_changeset(changeset_name):
            return False
    
    # Apply changeset to create config.plist (optional)
    if apply_changeset:
        log(f"Applying changeset: {changeset_name}")
        apply_script = pm.scripts / 'apply-changeset.py'
        if not run_command(f'python3.11 "{apply_script}" "{changeset_name}"', "Applying changeset"):
            error("Failed to apply changeset")
            return False
    
    # Prune kexts based on changeset
    if not manage_changeset_kexts(changeset_name, target_dir):
        error("Failed to manage kexts for changeset")
        return False
    
    # Copy drivers specified in changeset
    if not manage_changeset_drivers(changeset_name, target_dir):
        error("Failed to manage drivers for changeset")
        return False
    
    # Ensure config exists (validation handled by caller if desired)
    log("Ensuring final EFI structure has config.plist...")
    config_file = target_dir / 'OC' / 'config.plist'
    if not config_file.exists():
        error(f"Config file not found: {config_file}")
        return False
    
    # Clean up any previous changeset files
    efi_root = target_dir.parent
    oc_dir = target_dir / 'OC'
    
    # Remove previous changeset touch files in EFI root
    try:
        # Prefer new *.changeset markers; also clean legacy markers (no suffix)
        removed = 0
        for item in efi_root.iterdir():
            if item.is_file():
                if item.suffix == '.changeset' or (not item.name.startswith('.') and item.suffix == ''):
                    try:
                        item.unlink()
                        removed += 1
                    except Exception:
                        pass
        if removed:
            log(f"Removed {removed} previous changeset identifier file(s)")
    except Exception as e:
        warn(f"Failed to clean previous changeset identifiers: {e}")
    
    # Remove previous changeset YAML files in OC directory
    try:
        for item in oc_dir.glob('*.yaml'):
            if item.name != 'config.plist':  # Safety check
                item.unlink()
                log(f"Removed previous changeset YAML: {item.name}")
    except Exception as e:
        warn(f"Failed to clean previous changeset YAML files: {e}")
    
    # Copy changeset YAML file to EFI/OC directory
    changeset_yaml_path = pm.changesets / f"{changeset_name}.yaml"
    target_changeset_path = target_dir / 'OC' / f"{changeset_name}.yaml"
    try:
        if changeset_yaml_path.exists():
            shutil.copy2(changeset_yaml_path, target_changeset_path)
            log(f"✓ Copied changeset file to EFI/OC: {changeset_name}.yaml")
        else:
            warn(f"Changeset YAML file not found: {changeset_yaml_path}")
    except Exception as e:
        warn(f"Failed to copy changeset YAML file: {e}")
    
    # Create changeset identifier file in EFI root with .changeset extension
    changeset_file = target_dir.parent / f"{changeset_name}.changeset"
    try:
        # Touch (create or update mtime)
        changeset_file.touch()
        log(f"✓ Set changeset identifier: {changeset_file.name}")
    except Exception as e:
        warn(f"Failed to create changeset identifier file: {e}")
    
    log("✓ Complete EFI structure built successfully")
    return True

def copy_efi_for_build(source_efi_dir, target_build_dir, force_clean=True):
    """
    Copy EFI structure for build processes (ISO/USB).
    
    Args:
        source_efi_dir: Source EFI directory (typically out/efi/EFI)
        target_build_dir: Target build directory (typically out/build/efi)
        force_clean: Whether to clean target before copying
        
    Returns:
        bool: True if successful, False otherwise
    """
    source_efi = Path(source_efi_dir)
    target_build = Path(target_build_dir)
    
    if not source_efi.exists():
        error(f"Source EFI directory not found: {source_efi}")
        return False


def _validate_config_if_available() -> bool:
    """Run config validation if ocvalidate is available."""
    validate_script = pm.scripts / 'validate-config.py'
    if pm.ocvalidate.exists() and validate_script.exists():
        return run_command(f'python3.11 "{validate_script}"', "Validating configuration")
    if not pm.ocvalidate.exists():
        warn("Skipping validation (ocvalidate not available)")
    return True


def build_efi_then_validate(changeset_name: str, force_rebuild=False, no_validate=False, apply_changeset: bool = True) -> bool:
    """Ensure EFI structure is built for a changeset and optionally validate it."""
    if not build_complete_efi_structure(changeset_name=changeset_name, force_rebuild=force_rebuild, apply_changeset=apply_changeset):
        error("Failed to build complete EFI structure")
        return False
    if not no_validate and not _validate_config_if_available():
        error("Configuration validation failed")
        return False
    return True


def build_iso_artifact(changeset_name: str, force_rebuild=False, no_validate=False, apply_changeset: bool = True) -> bool:
    """Build EFI then package ISO to pm.opencore_iso using bin/build_isos.sh"""
    log("Building OpenCore ISO...")
    ocvalidate_path = pm.ocvalidate
    if not ocvalidate_path.exists():
        error("OpenCore tools not found")
        error(f"Expected ocvalidate at: {ocvalidate_path}")
        error("Please run './ozzy fetch' first to download OpenCore assets")
        return False

    if not build_efi_then_validate(changeset_name, force_rebuild, no_validate, apply_changeset=apply_changeset):
        return False

    # Ensure build script exists and run it (El Torito handled there)
    build_script = pm.bin / 'build_isos.sh'
    from . import validate_file_exists
    validate_file_exists(build_script, "Build script")
    run_command(f'chmod +x "{build_script}"')
    if not run_command(f'bash "{build_script}"', "Building OpenCore ISO"):
        error("ISO build script failed")
        return False
    if pm.opencore_iso.exists():
        log(f"OpenCore ISO created: {pm.opencore_iso}")
        return True
    error("ISO build completed but file not found")
    error(f"Expected ISO at: {pm.opencore_iso}")
    return False


def build_img_artifact(changeset_name: str, force_rebuild=False, no_validate=False, apply_changeset: bool = True) -> bool:
    """Build EFI then create a 50MB .img under build_root."""
    log("Building OpenCore IMG...")
    ocvalidate_path = pm.ocvalidate
    if not ocvalidate_path.exists():
        error("OpenCore tools not found")
        error(f"Expected ocvalidate at: {ocvalidate_path}")
        error("Please run './ozzy fetch' first to download OpenCore assets")
        return False

    if not build_efi_then_validate(changeset_name, force_rebuild, no_validate, apply_changeset=apply_changeset):
        return False

    source_efi = pm.efi_build / 'EFI'
    if not source_efi.exists():
        error(f"Source EFI structure not found: {source_efi}")
        return False

    img_filename = f'opencore-{changeset_name}.img'
    img_path = pm.build_root / img_filename

    # Remove existing files
    if img_path.exists():
        img_path.unlink()
    dmg_path = pm.build_root / f'{img_filename}.dmg'
    if dmg_path.exists():
        dmg_path.unlink()

    # macOS approach using hdiutil, else Linux loopback
    import sys as _sys
    import subprocess as _sp
    if _sys.platform == 'darwin':
        log("Creating disk image with hdiutil...")
        temp_name = f'opencore-{changeset_name}'
        temp_path = pm.build_root / temp_name
        cmd = f'hdiutil create -size 50m -fs MS-DOS -volname "OZZY-OC" -layout MBRSPUD "{temp_path}"'
        if not run_command(cmd, "Creating disk image"):
            return False
        created_dmg = pm.build_root / f'{temp_name}.dmg'
        if created_dmg.exists():
            created_dmg.rename(img_path)
            log(f"Renamed {created_dmg.name} to {img_path.name}")
        else:
            error(f"Expected DMG file not found: {created_dmg}")
            return False
        # Mount, copy EFI, then detach
        log("Mounting disk image...")
        result = _sp.run(['hdiutil', 'attach', str(img_path)], capture_output=True, text=True)
        if result.returncode != 0:
            error(f"Failed to attach disk image: {result.stderr}")
            return False
        mount_point = "/Volumes/OZZY-OC"
        try:
            log("Copying EFI structure to disk image...")
            if not run_command(f'cp -R "{source_efi}" "{mount_point}/"', "Copying EFI files"):
                return False
            if not run_command(f'chmod -R 755 "{mount_point}/EFI"', "Setting permissions"):
                return False
            # Copy changeset marker(s) to image root if present
            for marker in pm.efi_build.glob('*.changeset'):
                try:
                    _sp.run(['cp', str(marker), mount_point], check=True, capture_output=True)
                except Exception:
                    pass
        finally:
            log("Unmounting disk image...")
            _sp.run(['hdiutil', 'detach', mount_point], capture_output=True, check=False)
    else:
        log("Creating 50MB raw disk image...")
        if not run_command(f'dd if=/dev/zero of="{img_path}" bs=1m count=50', "Creating disk image"):
            return False
        log("Formatting disk image as FAT32...")
        if not run_command(f'mkfs.fat -F 32 -n "OZZY-OC" "{img_path}"', "Formatting disk image"):
            return False
        log("Mounting disk image and copying EFI files...")
        import tempfile as _tf
        with _tf.TemporaryDirectory() as temp_mount:
            if not run_command(f'sudo mount -o loop "{img_path}" "{temp_mount}"', "Mounting disk image"):
                return False
            try:
                if not run_command(f'sudo cp -R "{source_efi}"/* "{temp_mount}/"', "Copying EFI files"):
                    return False
                if not run_command(f'sudo chmod -R 755 "{temp_mount}/EFI"', "Setting permissions"):
                    return False
                # Copy changeset marker(s) to image root if present
                for marker in pm.efi_build.glob('*.changeset'):
                    _sp.run(['sudo', 'cp', str(marker), temp_mount], capture_output=True, check=False)
            finally:
                log("Unmounting disk image...")
                _sp.run(['sudo', 'umount', temp_mount], capture_output=True, check=False)

    log(f"✓ OpenCore IMG built successfully: {img_path}")
    return True
    
    # Clean target if requested
    if force_clean and (target_build / 'EFI').exists():
        log("Cleaning existing build EFI structure...")
        shutil.rmtree(target_build / 'EFI')
    
    # Copy EFI structure to build directory
    log(f"Copying EFI structure to build directory...")
    try:
        ensure_directory(target_build)
        shutil.copytree(source_efi, target_build / 'EFI', dirs_exist_ok=False)
        log("✓ EFI structure copied to build directory")
        return True
    except Exception as e:
        error(f"Failed to copy EFI structure: {e}")
        return False
