#!/usr/bin/env python3

import sys
import json
import os
import subprocess
import shutil
import urllib.request
import zipfile
import tempfile
import hashlib
from pathlib import Path

def ensure_command(cmd):
    """Check if a command is available"""
    if not shutil.which(cmd):
        print(f"ERROR: Missing required command: {cmd}")
        sys.exit(1)

def main():
    # Setup paths
    ROOT = Path(__file__).parent.parent.resolve()
    SRC = ROOT / "config" / "sources.json"
    OUT = ROOT / "out"
    OUT.mkdir(exist_ok=True)

    # Cache directory for all downloads
    CACHE = OUT / "cache"
    CACHE.mkdir(exist_ok=True)

    # New path structure - everything under out/build/
    BUILD = OUT / "build"
    BUILD.mkdir(exist_ok=True)
    
    EFIB = BUILD / "efi" / "EFI" / "OC"
    EFIB.mkdir(parents=True, exist_ok=True)
    
    BOOT = BUILD / "efi" / "EFI" / "BOOT"
    BOOT.mkdir(parents=True, exist_ok=True)

    # Create required subdirectories
    (BUILD / "efi" / "EFI" / "OC" / "Drivers").mkdir(parents=True, exist_ok=True)
    (BUILD / "efi" / "EFI" / "OC" / "Tools").mkdir(parents=True, exist_ok=True)
    (BUILD / "efi" / "EFI" / "OC" / "Kexts").mkdir(parents=True, exist_ok=True)
    (BUILD / "efi" / "EFI" / "OC" / "ACPI").mkdir(parents=True, exist_ok=True)

    # Check required commands
    for cmd in ['git', 'unzip']:
        ensure_command(cmd)

    # Load sources configuration
    with open(SRC) as f:
        config = json.load(f)

    # Get OpenCore version and repo
    oc_version = config["opencore"]["version"]
    oc_repo = config["opencore"]["repo"]

    print(f"[*] Fetching OpenCorePkg {oc_version} via SSH Git")
    
    # Cache directory for this specific version
    oc_cache_dir = CACHE / f"opencore-{oc_version}"
    
    # Check if we already have this version cached
    if oc_cache_dir.exists() and (oc_cache_dir / "X64").exists():
        print(f"[✓] Using cached OpenCore {oc_version}")
        oc_build_dir = OUT / "opencore"
        if oc_build_dir.exists():
            shutil.rmtree(oc_build_dir)
        shutil.copytree(oc_cache_dir, oc_build_dir)
    else:
        print(f"[*] Downloading and caching OpenCore {oc_version}...")
        
        # Clone the repository using SSH if it doesn't exist, otherwise reset it
        repo_dir = CACHE / "opencore-repo"
        ssh_repo_url = f"git@github.com:{oc_repo}.git"
        
        if not repo_dir.exists():
            print("[*] Cloning OpenCorePkg repository via SSH (shallow)...")
            try:
                subprocess.run([
                    'git', 'clone', '--depth', '1', '--recurse-submodules', '--shallow-submodules',
                    ssh_repo_url, str(repo_dir)
                ], check=True)
            except subprocess.CalledProcessError as e:
                print(f"[!] SSH clone failed, falling back to HTTPS: {e}")
                https_repo_url = f"https://github.com/{oc_repo}.git"
                subprocess.run([
                    'git', 'clone', '--depth', '1', '--recurse-submodules', '--shallow-submodules',
                    https_repo_url, str(repo_dir)
                ], check=True)
        else:
            print("[*] Resetting existing OpenCorePkg repository...")
            subprocess.run(['git', '-C', str(repo_dir), 'reset', '--hard', 'HEAD'], check=True)
            subprocess.run(['git', '-C', str(repo_dir), 'clean', '-fd'], check=True)

        os.chdir(repo_dir)
        
        # Ensure we're on the right tag/version
        print(f"[*] Ensuring we're on tag/version {oc_version}")
        
        # Check if tag exists
        result = subprocess.run(['git', 'tag', '-l'], capture_output=True, text=True)
        if oc_version in result.stdout.split('\n'):
            print(f"[*] Checking out tag {oc_version}")
            try:
                subprocess.run(['git', 'checkout', oc_version], check=True, capture_output=True)
            except subprocess.CalledProcessError:
                print(f"[*] Fetching specific tag {oc_version}")
                subprocess.run(['git', 'fetch', '--depth', '1', 'origin', 'tag', oc_version], check=True)
                subprocess.run(['git', 'checkout', oc_version], check=True)
        else:
            print(f"[!] Tag {oc_version} not found, using HEAD")

        os.chdir(ROOT)

        # Download pre-built release and cache it
        print("[*] No pre-built binaries found, downloading release...")
        
        release_url = f"https://github.com/{oc_repo}/releases/download/{oc_version}/OpenCore-{oc_version}-RELEASE.zip"
        cached_zip = CACHE / f"OpenCore-{oc_version}-RELEASE.zip"
        
        if not cached_zip.exists():
            print(f"[*] Downloading: {release_url}")
            try:
                urllib.request.urlretrieve(release_url, cached_zip)
                print(f"[✓] Cached OpenCore release as {cached_zip.name}")
            except Exception as e:
                print(f"[!] Failed to download pre-built release: {e}")
                sys.exit(1)
        else:
            print(f"[✓] Using cached zip: {cached_zip.name}")
        
        # Extract to cache
        with zipfile.ZipFile(cached_zip, 'r') as zip_ref:
            zip_ref.extractall(oc_cache_dir)
        
        # Copy from cache to working directory
        oc_build_dir = OUT / "opencore"
        if oc_build_dir.exists():
            shutil.rmtree(oc_build_dir)
        shutil.copytree(oc_cache_dir, oc_build_dir)

    # Copy OpenCore files from the built release
    if (oc_build_dir / "X64").exists():
        # Standard OpenCore build structure
        oc_files_dir = oc_build_dir / "X64"
    elif (oc_build_dir / "IA32_X64").exists():
        # Alternative build structure
        oc_files_dir = oc_build_dir / "IA32_X64"
    else:
        print("[!] Could not find OpenCore build files in expected structure")
        print("Available directories:")
        for item in oc_build_dir.iterdir():
            print(f"  {item}")
        sys.exit(1)

    print(f"[*] Copying OpenCore files from {oc_files_dir}")

    # Copy essential OpenCore files

    opencore_efi = oc_files_dir / "EFI" / "OC" / "OpenCore.efi"
    if opencore_efi.exists():
        shutil.copy2(opencore_efi, EFIB / "OpenCore.efi")
    else:
        print(f"[!] OpenCore.efi not found in {oc_files_dir}/EFI/OC/")
        sys.exit(1)

    bootx64_efi = oc_files_dir / "EFI" / "BOOT" / "BOOTx64.efi"
    if bootx64_efi.exists():
        shutil.copy2(bootx64_efi, BOOT / "BOOTx64.efi")
    else:
        print(f"[!] BOOTx64.efi not found in {oc_files_dir}/EFI/BOOT/")
        sys.exit(1)

    # Ensure ocvalidate and macserial are executable after extraction/copy
    ocvalidate_bin = (OUT / "opencore" / "Utilities" / "ocvalidate" / "ocvalidate")
    macserial_bin = (OUT / "opencore" / "Utilities" / "macserial" / "macserial")
    if ocvalidate_bin.exists():
        subprocess.run(["chmod", "+x", str(ocvalidate_bin)])
    if macserial_bin.exists():
        subprocess.run(["chmod", "+x", str(macserial_bin)])

    openruntime_efi = oc_files_dir / "EFI" / "OC" / "Drivers" / "OpenRuntime.efi"
    if openruntime_efi.exists():
        shutil.copy2(openruntime_efi, BUILD / "efi" / "EFI" / "OC" / "Drivers" / "OpenRuntime.efi")
    else:
        print("[!] OpenRuntime.efi not found")
        sys.exit(1)

    # Copy tools (these may not exist in all builds)
    openshell_efi = oc_files_dir / "EFI" / "OC" / "Tools" / "OpenShell.efi"
    if openshell_efi.exists():
        shutil.copy2(openshell_efi, BUILD / "efi" / "EFI" / "OC" / "Tools" / "OpenShell.efi")

    cleannvram_efi = oc_files_dir / "EFI" / "OC" / "Tools" / "CleanNvram.efi"
    if cleannvram_efi.exists():
        shutil.copy2(cleannvram_efi, BUILD / "efi" / "EFI" / "OC" / "Tools" / "CleanNvram.efi")

    # Fetch kexts via GitHub releases
    print("[*] Fetching kexts via GitHub releases")
    fetch_kexts(config, OUT, BUILD / "efi" / "EFI" / "OC" / "Kexts")

    # Fetch drivers from OcBinaryData
    print("[*] Fetching drivers from OcBinaryData")
    fetch_drivers(config, OUT, BUILD / "efi" / "EFI" / "OC" / "Drivers")

    # Fetch AMD Vanilla patches
    print("[*] Fetching AMD Vanilla patches")
    fetch_amd_vanilla(config, OUT)
    
    # Process local assets (zip files)
    print("[*] Processing local assets")
    process_local_assets(ROOT / "assets", BUILD / "efi" / "EFI" / "OC" / "Kexts")

    print("[*] Assets ready.")

def fetch_kexts(config, out_dir, dst_dir):
    """Fetch kexts from GitHub releases with proper caching"""
    # Create cache directory - use original kext-cache location
    cache_dir = out_dir / "kext-cache"
    cache_dir.mkdir(exist_ok=True)

    for kext in config["kexts"]:
        repo = kext["repo"]
        name = kext["name"]
        build_type = kext.get("build_type", "RELEASE")  # Default to RELEASE if not specified
        
        print(f"[*] Processing {name} from {repo} ({build_type} build)")
        
        # Check if we already have this kext cached
        # Look for existing cache files with the old naming pattern: acidanthera_Lilu-Lilu-1.7.1-RELEASE.zip-hash.zip
        repo_name = repo.replace('/', '_')
        kext_base_name = name.replace('.kext', '')  # Strip .kext suffix for pattern matching
        existing_cache = list(cache_dir.glob(f"{repo_name}-{kext_base_name}-*-{build_type}.zip-*.zip"))
        
        if existing_cache:
            print(f"[✓] Using cached {name}-{build_type}")
            cached_zip = existing_cache[0]
            
            # Extract kext from cached zip
            try:
                with zipfile.ZipFile(cached_zip, 'r') as zip_ref:
                    # Look for .kext directories in the zip
                    for item in zip_ref.namelist():
                        if item.endswith('.kext/') or (item.endswith('.kext') and '/' not in item):
                            # Handle directory names that end with /
                            if item.endswith('/'):
                                kext_name = item.rstrip('/').split('/')[-1]
                            else:
                                kext_name = item.split('/')[-1] if '/' in item else item
                            
                            # Check both full name and base name (without .kext)
                            if kext_name == name or kext_name == kext_base_name or kext_name == kext_base_name + '.kext':
                                # Check if this kext is nested inside a Kexts/ directory
                                if item.startswith('Kexts/'):
                                    # Extract only the specific kext, avoiding nested Kexts/Kexts/ structure
                                    kext_dir_name = item.rstrip('/').split('/')[-1]  # e.g., "VirtualSMC.kext"
                                    
                                    # Only extract .kext, not .dSYM unless it's a DEBUG build
                                    if build_type == "DEBUG":
                                        # For DEBUG builds, extract both .kext and .dSYM
                                        members_to_extract = [m for m in zip_ref.namelist() if m.startswith(f'Kexts/{kext_dir_name}')]
                                    else:
                                        # For RELEASE builds, only extract .kext (no debug symbols)
                                        members_to_extract = [m for m in zip_ref.namelist() if m.startswith(f'Kexts/{kext_dir_name}/') and not '.dSYM' in m]
                                    
                                    # Extract to a temp location and then move to avoid nesting
                                    import tempfile
                                    with tempfile.TemporaryDirectory() as temp_dir:
                                        zip_ref.extractall(temp_dir, members=members_to_extract)
                                        temp_kext_path = Path(temp_dir) / 'Kexts' / kext_dir_name
                                        final_kext_path = dst_dir / kext_dir_name
                                        
                                        if final_kext_path.exists():
                                            shutil.rmtree(final_kext_path)
                                        shutil.copytree(temp_kext_path, final_kext_path)
                                else:
                                    # Extract normally for kexts at root level
                                    if build_type == "DEBUG":
                                        # For DEBUG builds, extract both .kext and .dSYM
                                        members_to_extract = [m for m in zip_ref.namelist() if m.startswith(item.rstrip('/'))]
                                    else:
                                        # For RELEASE builds, only extract .kext (no debug symbols)
                                        members_to_extract = [m for m in zip_ref.namelist() if m.startswith(item.rstrip('/') + '/') and not '.dSYM' in m]
                                    
                                    zip_ref.extractall(dst_dir, members=members_to_extract)
                                
                                print(f"[✓] Installed {name} from cache")
                                break
                    else:
                        print(f"[!] Could not find {name} in {cached_zip}")
            except Exception as e:
                print(f"[!] Failed to extract {name}: {e}")
            continue
        
        print(f"[*] Downloading {name} from GitHub...")
        try:
                # Get latest release info from GitHub API
                api_url = f"https://api.github.com/repos/{repo}/releases/latest"
                with urllib.request.urlopen(api_url) as response:
                    release_data = json.load(response)
                
                # Find the release asset based on build type
                assets = release_data.get("assets", [])
                download_url = None
                asset_name = None
                
                # Look for assets matching the build type preference
                for asset in assets:
                    if asset["name"].endswith(".zip"):
                        # Check if this asset matches our build type preference
                        if build_type == "DEBUG" and "-DEBUG" in asset["name"]:
                            download_url = asset["browser_download_url"]
                            asset_name = asset["name"]
                            break
                        elif build_type == "RELEASE" and ("-RELEASE" in asset["name"] or "-DEBUG" not in asset["name"]):
                            download_url = asset["browser_download_url"]
                            asset_name = asset["name"]
                            break
                
                if not download_url:
                    print(f"[!] No suitable {build_type} build found for {name}")
                    continue
                
                # Cache the download
                cached_zip = cache_dir / asset_name
                urllib.request.urlretrieve(download_url, cached_zip)
                print(f"[✓] Cached {name} as {asset_name}")
                
                # Extract kext from downloaded zip
                try:
                    with zipfile.ZipFile(cached_zip, 'r') as zip_ref:
                        # Look for .kext directories in the zip
                        for item in zip_ref.namelist():
                            if item.endswith('.kext/') or (item.endswith('.kext') and '/' not in item):
                                # Handle directory names that end with /
                                if item.endswith('/'):
                                    kext_name = item.rstrip('/').split('/')[-1]
                                else:
                                    kext_name = item.split('/')[-1] if '/' in item else item
                                
                                # Check both full name and base name (without .kext)
                                if kext_name == name or kext_name == kext_base_name or kext_name == kext_base_name + '.kext':
                                    # Check if this kext is nested inside a Kexts/ directory
                                    if item.startswith('Kexts/'):
                                        # Extract only the specific kext, avoiding nested Kexts/Kexts/ structure
                                        kext_dir_name = item.rstrip('/').split('/')[-1]  # e.g., "VirtualSMC.kext"
                                        
                                        # Only extract .kext, not .dSYM unless it's a DEBUG build
                                        if build_type == "DEBUG":
                                            # For DEBUG builds, extract both .kext and .dSYM
                                            members_to_extract = [m for m in zip_ref.namelist() if m.startswith(f'Kexts/{kext_dir_name}')]
                                        else:
                                            # For RELEASE builds, only extract .kext (no debug symbols)
                                            members_to_extract = [m for m in zip_ref.namelist() if m.startswith(f'Kexts/{kext_dir_name}/') and not '.dSYM' in m]
                                        
                                        # Extract to a temp location and then move to avoid nesting
                                        with tempfile.TemporaryDirectory() as temp_dir:
                                            zip_ref.extractall(temp_dir, members=members_to_extract)
                                            temp_kext_path = Path(temp_dir) / 'Kexts' / kext_dir_name
                                            final_kext_path = dst_dir / kext_dir_name
                                            
                                            if final_kext_path.exists():
                                                shutil.rmtree(final_kext_path)
                                            shutil.copytree(temp_kext_path, final_kext_path)
                                    else:
                                        # Extract normally for kexts at root level
                                        if build_type == "DEBUG":
                                            # For DEBUG builds, extract both .kext and .dSYM
                                            members_to_extract = [m for m in zip_ref.namelist() if m.startswith(item.rstrip('/'))]
                                        else:
                                            # For RELEASE builds, only extract .kext (no debug symbols)
                                            members_to_extract = [m for m in zip_ref.namelist() if m.startswith(item.rstrip('/') + '/') and not '.dSYM' in m]
                                        
                                        zip_ref.extractall(dst_dir, members=members_to_extract)
                                    
                                    print(f"[✓] Installed {name} from download")
                                    break
                        else:
                            print(f"[!] Could not find {name} in {cached_zip}")
                except Exception as e:
                    print(f"[!] Failed to extract {name}: {e}")
                    
        except Exception as e:
            print(f"[!] Failed to download {name} release: {e}")
            print(f"[!] You may need to download it manually")

def fetch_drivers(config, out_dir, drivers_dir):
    """Fetch drivers from OcBinaryData with proper caching"""
    if 'ocbinarydata' not in config:
        print("[*] No OcBinaryData sources configured")
        return

    ocbd = config['ocbinarydata']
    repo = ocbd['repo']
    drivers = ocbd.get('drivers', [])

    if not drivers:
        print("[*] No OcBinaryData drivers configured")
        return

    # Check cache first
    cache_dir = out_dir / "cache" / "ocbinarydata"
    repo_dir = cache_dir / 'ocbinarydata-repo'
    
    ssh_repo_url = f"git@github.com:{repo}.git"
    
    if not repo_dir.exists():
        print(f"[*] Cloning {repo} repository via SSH (shallow)...")
        try:
            subprocess.run(['git', 'clone', '--depth', '1', ssh_repo_url, str(repo_dir)], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[!] SSH clone failed, falling back to HTTPS: {e}")
            https_repo_url = f"https://github.com/{repo}.git"
            subprocess.run(['git', 'clone', '--depth', '1', https_repo_url, str(repo_dir)], check=True)
    else:
        print(f"[*] Updating {repo} repository...")
        # Ensure remote is SSH and pull
        subprocess.run(['git', '-C', str(repo_dir), 'remote', 'set-url', 'origin', ssh_repo_url], check=True)
        subprocess.run(['git', '-C', str(repo_dir), 'pull', '--depth', '1'], check=True)

    # Copy each driver
    for driver in drivers:
        driver_name = driver['name']
        driver_path = driver['path']
        
        src_file = repo_dir / driver_path
        if src_file.exists():
            dst_file = drivers_dir / driver_name
            shutil.copy2(src_file, dst_file)
            print(f"[✓] Copied {driver_name} from OcBinaryData")
        else:
            print(f"[!] Driver not found: {driver_path}")

def fetch_amd_vanilla(config, out_dir):
    """Fetch AMD Vanilla patches with proper caching"""
    if 'amd_vanilla' not in config:
        print("[*] No AMD Vanilla patches configured")
        return

    amd = config['amd_vanilla']
    repo = amd['repo']
    
    # Check cache first
    cache_dir = out_dir / "cache" / "amd-vanilla"
    repo_dir = cache_dir / 'amd-vanilla-repo'
    
    ssh_repo_url = f"git@github.com:{repo}.git"
    
    if not repo_dir.exists():
        print(f"[*] Cloning {repo} repository via SSH...")
        try:
            subprocess.run(['git', 'clone', ssh_repo_url, str(repo_dir)], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[!] SSH clone failed, falling back to HTTPS: {e}")
            https_repo_url = f"https://github.com/{repo}.git"
            subprocess.run(['git', 'clone', https_repo_url, str(repo_dir)], check=True)
    else:
        print(f"[*] Updating {repo} repository...")
        # Ensure remote is SSH and update
        subprocess.run(['git', '-C', str(repo_dir), 'remote', 'set-url', 'origin', ssh_repo_url], check=True)
        subprocess.run(['git', '-C', str(repo_dir), 'fetch'], check=True)
        subprocess.run(['git', '-C', str(repo_dir), 'reset', '--hard', 'origin/master'], check=True)

    # Copy patches to main output directory for use by apply-changeset
    patches_file = repo_dir / 'patches.plist'
    if patches_file.exists():
        dst_file = out_dir / 'amd-vanilla-patches.plist'
        shutil.copy2(patches_file, dst_file)
        print(f"[✓] AMD Vanilla patches available at {repo_dir}")
        print(f"[✓] Cached AMD Vanilla patches as {dst_file}")
    else:
        print(f"[!] AMD Vanilla patches not found in {repo_dir}")

def process_local_assets(assets_dir, kexts_dir):
    """Process local asset files (like .kext.zip files)"""
    if not assets_dir.exists():
        print("[*] No local assets directory found")
        return
    
    # Find all .kext.zip files in assets directory
    kext_zips = list(assets_dir.glob("*.kext.zip"))
    
    if not kext_zips:
        print("[*] No local kext zip files found")
        return
    
    print(f"[*] Found {len(kext_zips)} local kext zip files")
    
    for zip_file in kext_zips:
        kext_name = zip_file.name.replace(".zip", "")
        print(f"[*] Processing {kext_name} from local assets")
        
        try:
            with zipfile.ZipFile(zip_file, 'r') as zip_ref:
                # Extract to temp directory first
                with tempfile.TemporaryDirectory() as temp_dir:
                    zip_ref.extractall(temp_dir)
                    
                    # Find the kext directory
                    temp_path = Path(temp_dir)
                    kext_dirs = list(temp_path.glob("**/*.kext"))
                    
                    if kext_dirs:
                        src_kext = kext_dirs[0]
                        dst_kext = kexts_dir / src_kext.name
                        
                        # Remove existing if present
                        if dst_kext.exists():
                            shutil.rmtree(dst_kext)
                        
                        # Copy the kext
                        shutil.copytree(src_kext, dst_kext)
                        print(f"[✓] Installed {src_kext.name} from local assets")
                    else:
                        print(f"[!] No .kext directory found in {zip_file}")
                        
        except Exception as e:
            print(f"[!] Failed to process {zip_file}: {e}")

if __name__ == "__main__":
    main()
