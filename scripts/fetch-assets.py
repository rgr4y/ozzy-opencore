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

    print(f"[*] Fetching OpenCorePkg {oc_version} via Git")
    
    # Clone the repository if it doesn't exist, otherwise reset it
    repo_dir = OUT / "opencore-repo"
    if not repo_dir.exists():
        print("[*] Cloning OpenCorePkg repository (shallow)...")
        subprocess.run([
            'git', 'clone', '--depth', '1', '--recurse-submodules', '--shallow-submodules',
            f'https://github.com/{oc_repo}.git', str(repo_dir)
        ], check=True)
    else:
        print("[*] Resetting existing OpenCorePkg repository...")
        subprocess.run(['git', '-C', str(repo_dir), 'reset', '--hard', 'HEAD'], check=True)
        subprocess.run(['git', '-C', str(repo_dir), 'clean', '-fd'], check=True)
        # Update submodules if they exist
        gitmodules = repo_dir / ".gitmodules"
        if gitmodules.exists():
            subprocess.run([
                'git', '-C', str(repo_dir), 'submodule', 'foreach', '--recursive',
                'git reset --hard HEAD && git clean -fd'
            ], check=True)

    os.chdir(repo_dir)
    
    # For existing repos, we already have the tag from the shallow clone
    # Just ensure we're on the right tag/version
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
        # Check if it's a branch
        result = subprocess.run(['git', 'rev-parse', '--verify', f'origin/{oc_version}'], 
                              capture_output=True)
        if result.returncode == 0:
            print(f"[*] Checking out branch {oc_version}")
            subprocess.run(['git', 'checkout', '-B', oc_version, f'origin/{oc_version}'], check=True)
        else:
            print(f"[!] Tag/branch {oc_version} not found, using HEAD")
            subprocess.run(['git', 'checkout', 'HEAD'], check=True)

    # Reset to ensure clean state and update submodules
    subprocess.run(['git', 'reset', '--hard', 'HEAD'], check=True)
    subprocess.run(['git', 'clean', '-fd'], check=True)
    if (repo_dir / ".gitmodules").exists():
        subprocess.run(['git', 'submodule', 'update', '--init', '--recursive', '--depth', '1'], check=True)

    os.chdir(ROOT)

    # Build the release if Binaries directory doesn't exist
    binaries_dir = repo_dir / "Binaries"
    if not binaries_dir.exists():
        print("[*] No pre-built binaries found, downloading release...")
        # Download pre-built release from GitHub with caching
        cache_dir = OUT / "opencore-cache"
        cache_dir.mkdir(exist_ok=True)
        
        release_url = f"https://github.com/{oc_repo}/releases/download/{oc_version}/OpenCore-{oc_version}-RELEASE.zip"
        cached_file = cache_dir / f"OpenCore-{oc_version}-RELEASE.zip"
        
        if cached_file.exists():
            print(f"[*] Using cached OpenCore {oc_version} release")
            oc_zip_path = cached_file
        else:
            print(f"[*] Downloading: {release_url}")
            try:
                urllib.request.urlretrieve(release_url, cached_file)
                print(f"[*] Cached OpenCore release as {cached_file.name}")
                oc_zip_path = cached_file
            except Exception as e:
                print(f"[!] Failed to download pre-built release: {e}")
                print("[!] Please check the version in sources.json")
                sys.exit(1)
        
        oc_build_dir = OUT / "opencore"
        if oc_build_dir.exists():
            shutil.rmtree(oc_build_dir)
        
        with zipfile.ZipFile(oc_zip_path, 'r') as zip_ref:
            zip_ref.extractall(oc_build_dir)
    else:
        print("[*] Using existing build in Binaries directory")
        oc_build_dir = OUT / "opencore"
        if oc_build_dir.exists():
            shutil.rmtree(oc_build_dir)
        shutil.copytree(binaries_dir, oc_build_dir)

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

    # ResetNvramEntry.efi can be in different locations
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

    print("[*] Assets ready.")

def fetch_kexts(config, out_dir, dst_dir):
    """Fetch kexts from GitHub releases"""
    # Create cache directory
    cache_dir = out_dir / "kext-cache"
    cache_dir.mkdir(exist_ok=True)

    for kext in config["kexts"]:
        repo = kext["repo"]
        name = kext["name"]
        build_type = kext.get("build_type", "RELEASE")  # Default to RELEASE if not specified
        
        print(f"[*] Processing {name} from {repo} ({build_type} build)")
        
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
            
            # Fallback: if no specific build type found, take any zip
            if not download_url:
                for asset in assets:
                    if asset["name"].endswith(".zip"):
                        download_url = asset["browser_download_url"]
                        asset_name = asset["name"]
                        print(f"[!] {build_type} build not found, using fallback: {asset_name}")
                        break
            
            if not download_url:
                print(f"[!] No zip asset found for {name}, trying git approach...")
                continue
            
            # Generate cache filename based on download URL hash
            url_hash = hashlib.md5(download_url.encode()).hexdigest()[:8]
            cache_filename = f"{repo.replace('/', '_')}-{asset_name}-{url_hash}.zip"
            cached_zip_path = cache_dir / cache_filename
            
            # Check if we already have this release cached
            if cached_zip_path.exists():
                print(f"[✓] Using cached {asset_name}")
                zip_path = cached_zip_path
            else:
                # Download the release and cache it
                print(f"[*] Downloading {name} from {download_url}")
                
                with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as temp_file:
                    urllib.request.urlretrieve(download_url, temp_file.name)
                    temp_zip_path = temp_file.name
                
                # Move to cache
                shutil.move(temp_zip_path, cached_zip_path)
                zip_path = cached_zip_path
                print(f"[✓] Cached as {cache_filename}")
            
            # Extract and find the kext - use build type in directory name
            build_type_lower = build_type.lower()
            extract_dir = out_dir / f"kext-{build_type_lower}-{repo.replace('/', '_')}"
            
            # Clear extract directory first to avoid stale files
            if extract_dir.exists():
                shutil.rmtree(extract_dir)
            extract_dir.mkdir(parents=True, exist_ok=True)
            
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(extract_dir)
            
            # Clean up macOS metadata files after extraction
            for root, dirs, files in os.walk(extract_dir):
                # Remove macOS metadata files
                for file in files[:]:  # Use slice copy to modify during iteration
                    if file.startswith('._'):
                        os.remove(os.path.join(root, file))
                # Remove __MACOSX directories
                for dir_name in dirs[:]:  # Use slice copy to modify during iteration
                    if dir_name == '__MACOSX':
                        shutil.rmtree(os.path.join(root, dir_name))
                        dirs.remove(dir_name)
            
            # Find the kext in the extracted files
            kext_found = False
            for root, dirs, files in os.walk(extract_dir):
                # Look for a directory that ends with the exact kext name and contains Contents/Info.plist
                if root.endswith(name) and os.path.isfile(os.path.join(root, 'Contents', 'Info.plist')):
                    dst_path = dst_dir / name
                    if dst_path.exists():
                        shutil.rmtree(dst_path)
                    shutil.copytree(root, dst_path)
                    print(f"[✓] Installed {name} from {'cache' if cached_zip_path.exists() else 'download'}")
                    kext_found = True
                    break
            
            if not kext_found:
                print(f"[!] Could not find {name} in release archive")
                
        except Exception as e:
            print(f"[!] Failed to download {name} release: {e}")
            print(f"[!] You may need to download it manually")

def fetch_drivers(config, out_dir, drivers_dir):
    """Fetch drivers from OcBinaryData"""
    if 'ocbinarydata' not in config:
        print("[*] No OcBinaryData sources configured")
        return

    ocbd = config['ocbinarydata']
    repo = ocbd['repo']
    drivers = ocbd.get('drivers', [])

    if not drivers:
        print("[*] No OcBinaryData drivers configured")
        return

    # Clone or update OcBinaryData repository
    repo_dir = out_dir / 'ocbinarydata-repo'
    if not repo_dir.exists():
        print(f"[*] Cloning {repo} repository (shallow)...")
        subprocess.run(['git', 'clone', '--depth', '1', f'https://github.com/{repo}.git', str(repo_dir)], check=True)
    else:
        print(f"[*] Updating {repo} repository...")
        subprocess.run(['git', '-C', str(repo_dir), 'pull', '--depth', '1'], check=True)

    # Copy each driver
    for driver in drivers:
        driver_name = driver['name']
        driver_path = driver['path']
        
        src_file = repo_dir / driver_path
        dst_file = drivers_dir / driver_name
        
        if src_file.exists():
            shutil.copy2(src_file, dst_file)
            print(f"[✓] Copied {driver_name} from OcBinaryData")
        else:
            print(f"[!] {driver_name} not found at {driver_path} in OcBinaryData repository")

def fetch_amd_vanilla(config, out_dir):
    """Fetch AMD Vanilla patches"""
    if 'amd_vanilla' not in config:
        print("[*] No AMD Vanilla sources configured")
        return

    amd_config = config['amd_vanilla']
    repo = amd_config['repo']
    branch = amd_config.get('branch', 'master')
    patches_file = amd_config.get('patches_file', 'patches.plist')

    # Clone or update AMD Vanilla repository
    repo_dir = out_dir / 'amd-vanilla-repo'
    if not repo_dir.exists():
        print(f"[*] Cloning {repo} repository (shallow)...")
        subprocess.run(['git', 'clone', '--depth', '1', '--branch', branch, 
                       f'https://github.com/{repo}.git', str(repo_dir)], check=True)
    else:
        print(f"[*] Updating {repo} repository...")
        subprocess.run(['git', '-C', str(repo_dir), 'fetch', '--depth', '1', 'origin', branch], check=True)
        subprocess.run(['git', '-C', str(repo_dir), 'reset', '--hard', f'origin/{branch}'], check=True)

    # Verify patches file exists
    patches_path = repo_dir / patches_file
    if patches_path.exists():
        print(f"[✓] AMD Vanilla patches available at {patches_path}")
        
        # Create a symlink or copy to a known location for easy access
        patches_cache = out_dir / 'amd-vanilla-patches.plist'
        if patches_cache.exists() or patches_cache.is_symlink():
            patches_cache.unlink()
        shutil.copy2(patches_path, patches_cache)
        print(f"[✓] Cached AMD Vanilla patches as {patches_cache}")
    else:
        print(f"[!] {patches_file} not found in AMD Vanilla repository")
        sys.exit(1)

if __name__ == "__main__":
    main()
