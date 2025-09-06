#!/usr/bin/env bash

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/config/sources.json"
OUT="$ROOT/out"; mkdir -p "$OUT"

# New path structure - everything under out/build/
BUILD="$OUT/build"; mkdir -p "$BUILD"
EFIB="$BUILD/efi/EFI/OC"; mkdir -p "$EFIB"
BOOT="$BUILD/efi/EFI/BOOT"; mkdir -p "$BOOT"

# Create required subdirectories
mkdir -p "$BUILD/efi/EFI/OC/Drivers"
mkdir -p "$BUILD/efi/EFI/OC/Tools"
mkdir -p "$BUILD/efi/EFI/OC/Kexts"
mkdir -p "$BUILD/efi/EFI/OC/ACPI"

need(){ command -v "$1" >/dev/null 2>&1 || { echo "Missing $1"; exit 1; }; }
need git; need unzip; need python3

OC_VER=$(python3.11 - <<'PY' "$SRC"
import json,sys; print(json.load(open(sys.argv[1]))["opencore"]["version"])
PY
)
OC_REPO=$(python3.11 - <<'PY' "$SRC"
import json,sys; print(json.load(open(sys.argv[1]))["opencore"]["repo"])
PY
)

echo "[*] Fetching OpenCorePkg $OC_VER via Git"
# Clone the repository if it doesn't exist, otherwise reset it
REPO_DIR="$OUT/opencore-repo"
if [ ! -d "$REPO_DIR" ]; then
    echo "[*] Cloning OpenCorePkg repository (shallow)..."
    git clone --depth 1 --recurse-submodules --shallow-submodules "https://github.com/$OC_REPO.git" "$REPO_DIR"
else
    echo "[*] Resetting existing OpenCorePkg repository..."
    cd "$REPO_DIR" && git reset --hard HEAD && git clean -fd
    # Update submodules if they exist
    if [ -f .gitmodules ]; then
        git submodule foreach --recursive 'git reset --hard HEAD && git clean -fd'
    fi
fi

cd "$REPO_DIR"
# For existing repos, we already have the tag from the shallow clone
# Just ensure we're on the right tag/version
echo "[*] Ensuring we're on tag/version $OC_VER"
if git tag -l | grep -q "^$OC_VER$"; then
    echo "[*] Checking out tag $OC_VER"
    git checkout "$OC_VER" 2>/dev/null || {
        echo "[*] Fetching specific tag $OC_VER"
        git fetch --depth 1 origin tag "$OC_VER"
        git checkout "$OC_VER"
    }
elif git rev-parse --verify "origin/$OC_VER" >/dev/null 2>&1; then
    echo "[*] Checking out branch $OC_VER"
    git checkout -B "$OC_VER" "origin/$OC_VER"
else
    echo "[!] Tag/branch $OC_VER not found, using HEAD"
    git checkout HEAD
fi

# Reset to ensure clean state and update submodules
git reset --hard HEAD
git clean -fd
if [ -f .gitmodules ]; then
    git submodule update --init --recursive --depth 1
fi

# Build the release if Binaries directory doesn't exist
if [ ! -d "Binaries" ]; then
    echo "[*] No pre-built binaries found, downloading release..."
    # Download pre-built release from GitHub with caching
    CACHE_DIR="$OUT/opencore-cache"
    mkdir -p "$CACHE_DIR"
    
    RELEASE_URL="https://github.com/$OC_REPO/releases/download/$OC_VER/OpenCore-$OC_VER-RELEASE.zip"
    CACHED_FILE="$CACHE_DIR/OpenCore-$OC_VER-RELEASE.zip"
    
    if [ -f "$CACHED_FILE" ]; then
        echo "[*] Using cached OpenCore $OC_VER release"
        OC_ZIP_PATH="$CACHED_FILE"
    else
        echo "[*] Downloading: $RELEASE_URL"
        curl -fL "$RELEASE_URL" -o "$CACHED_FILE" || {
            echo "[!] Failed to download pre-built release. Please check the version in sources.json"
            exit 1
        }
        echo "[*] Cached OpenCore release as $(basename "$CACHED_FILE")"
        OC_ZIP_PATH="$CACHED_FILE"
    fi
    
    cd "$OUT"
    rm -rf "$OUT/opencore"  # Clean existing extraction
    unzip -o "$OC_ZIP_PATH" -d "$OUT/opencore"
    cd "$ROOT"
else
    echo "[*] Using existing build in Binaries directory"
    rm -rf "$OUT/opencore"
    cp -r "Binaries" "$OUT/opencore"
    cd "$ROOT"
fi
cd "$ROOT"

# Copy OpenCore files from the built release
OC_BUILD_DIR="$OUT/opencore"
if [ -d "$OC_BUILD_DIR/X64" ]; then
    # Standard OpenCore build structure
    OC_FILES_DIR="$OC_BUILD_DIR/X64"
elif [ -d "$OC_BUILD_DIR/IA32_X64" ]; then
    # Alternative build structure  
    OC_FILES_DIR="$OC_BUILD_DIR/IA32_X64"
else
    echo "[!] Could not find OpenCore build files in expected structure"
    ls -la "$OC_BUILD_DIR"
    exit 1
fi

echo "[*] Copying OpenCore files from $OC_FILES_DIR"

# Copy essential OpenCore files
if [ -f "$OC_FILES_DIR/EFI/OC/OpenCore.efi" ]; then
    cp -av "$OC_FILES_DIR/EFI/OC/OpenCore.efi" "$EFIB/"
else
    echo "[!] OpenCore.efi not found in $OC_FILES_DIR/EFI/OC/"
    exit 1
fi

if [ -f "$OC_FILES_DIR/EFI/BOOT/BOOTx64.efi" ]; then
    cp -av "$OC_FILES_DIR/EFI/BOOT/BOOTx64.efi" "$BOOT/"
else
    echo "[!] BOOTx64.efi not found in $OC_FILES_DIR/EFI/BOOT/"
    exit 1
fi

if [ -f "$OC_FILES_DIR/EFI/OC/Drivers/OpenRuntime.efi" ]; then
    cp -av "$OC_FILES_DIR/EFI/OC/Drivers/OpenRuntime.efi" "$BUILD/efi/EFI/OC/Drivers/"
else
    echo "[!] OpenRuntime.efi not found"
    exit 1
fi

# Copy tools (these may not exist in all builds)
[ -f "$OC_FILES_DIR/EFI/OC/Tools/OpenShell.efi" ] && cp -av "$OC_FILES_DIR/EFI/OC/Tools/OpenShell.efi" "$BUILD/efi/EFI/OC/Tools/"

# ResetNvramEntry.efi can be in different locations
for p in "$OC_FILES_DIR/EFI/OC/Tools/CleanNvram.efi"; do
  [ -f "$p" ] && cp -av "$p" "$BUILD/efi/EFI/OC/Tools/"
done

echo "[*] Fetching kexts via GitHub releases"
python3.11 - "$SRC" "$OUT" "$BUILD/efi/EFI/OC/Kexts" <<'PY'
import sys,json,os,subprocess,shutil,urllib.request,zipfile,tempfile,hashlib
cfg=json.load(open(sys.argv[1])); out=sys.argv[2]; dst=sys.argv[3]

# Create cache directory
cache_dir = os.path.join(out, "kext-cache")
os.makedirs(cache_dir, exist_ok=True)

for k in cfg["kexts"]:
    repo = k["repo"]
    name = k["name"]
    
    print(f"[*] Processing {name} from {repo}")
    
    try:
        # Get latest release info from GitHub API
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        with urllib.request.urlopen(api_url) as response:
            release_data = json.load(response)
        
        # Find the release asset (usually a .zip file)
        assets = release_data.get("assets", [])
        download_url = None
        asset_name = None
        
        for asset in assets:
            if asset["name"].endswith(".zip"):
                download_url = asset["browser_download_url"]
                asset_name = asset["name"]
                break
        
        if not download_url:
            print(f"[!] No zip asset found for {name}, trying git approach...")
            continue
        
        # Generate cache filename based on download URL hash
        url_hash = hashlib.md5(download_url.encode()).hexdigest()[:8]
        cache_filename = f"{repo.replace('/', '_')}-{asset_name}-{url_hash}.zip"
        cached_zip_path = os.path.join(cache_dir, cache_filename)
        
        # Check if we already have this release cached
        if os.path.exists(cached_zip_path):
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
        
        # Extract and find the kext
        extract_dir = os.path.join(out, f"kext-release-{repo.replace('/', '_')}")
        os.makedirs(extract_dir, exist_ok=True)
        
        # Clear extract directory first to avoid stale files
        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir)
        os.makedirs(extract_dir, exist_ok=True)
        
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
                dst_path = os.path.join(dst, name)
                if os.path.exists(dst_path):
                    shutil.rmtree(dst_path)
                shutil.copytree(root, dst_path)
                print(f"[✓] Installed {name} from {'cache' if os.path.exists(cached_zip_path) else 'download'}")
                kext_found = True
                break
        
        if not kext_found:
            print(f"[!] Could not find {name} in release archive")
            
    except Exception as e:
        print(f"[!] Failed to download {name} release: {e}")
        print(f"[!] You may need to download it manually")
PY

echo "[*] Fetching drivers from OcBinaryData"
python3 - "$SRC" "$OUT" "$BUILD/efi/EFI/OC/Drivers" <<'PY'
import sys,json,os,subprocess,shutil,urllib.request,hashlib

src_path, out_dir, drivers_dir = sys.argv[1], sys.argv[2], sys.argv[3]
with open(src_path) as f:
    sources = json.load(f)

if 'ocbinarydata' not in sources:
    print("[*] No OcBinaryData sources configured")
    sys.exit(0)

ocbd = sources['ocbinarydata']
repo = ocbd['repo']
drivers = ocbd.get('drivers', [])

if not drivers:
    print("[*] No OcBinaryData drivers configured")
    sys.exit(0)

# Clone or update OcBinaryData repository
repo_dir = os.path.join(out_dir, 'ocbinarydata-repo')
if not os.path.exists(repo_dir):
    print(f"[*] Cloning {repo} repository (shallow)...")
    subprocess.run(['git', 'clone', '--depth', '1', f'https://github.com/{repo}.git', repo_dir], check=True)
else:
    print(f"[*] Updating {repo} repository...")
    subprocess.run(['git', '-C', repo_dir, 'pull', '--depth', '1'], check=True)

# Copy each driver
for driver in drivers:
    driver_name = driver['name']
    driver_path = driver['path']
    
    src_file = os.path.join(repo_dir, driver_path)
    dst_file = os.path.join(drivers_dir, driver_name)
    
    if os.path.exists(src_file):
        shutil.copy2(src_file, dst_file)
        print(f"[✓] Copied {driver_name} from OcBinaryData")
    else:
        print(f"[!] {driver_name} not found at {driver_path} in OcBinaryData repository")
PY

echo "[*] Fetching AMD Vanilla patches"
python3 - "$SRC" "$OUT" <<'PY'
import sys,json,os,subprocess,shutil

src_path, out_dir = sys.argv[1], sys.argv[2]
with open(src_path) as f:
    sources = json.load(f)

if 'amd_vanilla' not in sources:
    print("[*] No AMD Vanilla sources configured")
    sys.exit(0)

amd_config = sources['amd_vanilla']
repo = amd_config['repo']
branch = amd_config.get('branch', 'master')
patches_file = amd_config.get('patches_file', 'patches.plist')

# Clone or update AMD Vanilla repository
repo_dir = os.path.join(out_dir, 'amd-vanilla-repo')
if not os.path.exists(repo_dir):
    print(f"[*] Cloning {repo} repository (shallow)...")
    subprocess.run(['git', 'clone', '--depth', '1', '--branch', branch, f'https://github.com/{repo}.git', repo_dir], check=True)
else:
    print(f"[*] Updating {repo} repository...")
    subprocess.run(['git', '-C', repo_dir, 'fetch', '--depth', '1', 'origin', branch], check=True)
    subprocess.run(['git', '-C', repo_dir, 'reset', '--hard', f'origin/{branch}'], check=True)

# Verify patches file exists
patches_path = os.path.join(repo_dir, patches_file)
if os.path.exists(patches_path):
    print(f"[✓] AMD Vanilla patches available at {patches_path}")
    
    # Create a symlink or copy to a known location for easy access
    patches_cache = os.path.join(out_dir, 'amd-vanilla-patches.plist')
    if os.path.exists(patches_cache) or os.path.islink(patches_cache):
        os.remove(patches_cache)
    shutil.copy2(patches_path, patches_cache)
    print(f"[✓] Cached AMD Vanilla patches as {patches_cache}")
else:
    print(f"[!] {patches_file} not found in AMD Vanilla repository")
    sys.exit(1)
PY

echo "[*] Assets ready."
