#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/out"; mkdir -p "$OUT"
BUILD="$OUT/build"
EFI_BUILD="$BUILD/efi"

build_iso() {
  local SRC="$1" ; local OUTISO="$2" ; local VOL="$3"
  
  # Check if xorriso is available (preferred for EFI boot)
  if command -v xorriso >/dev/null 2>&1; then
    echo "[*] Using xorriso for EFI bootable ISO creation"
    rm -f "$OUTISO" || true
    
    # Create EFI System Partition (ESP) image
    EFI_IMG="$OUT/efiboot.img"
    ESP_MOUNT="/Volumes/EFIBOOT"
    
    echo "[*] Creating 100MB EFI System Partition image..."
    dd if=/dev/zero of="$EFI_IMG" bs=1m count=100 2>/dev/null
    
    echo "[*] Formatting ESP as FAT16..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
      # macOS: Attach as a disk device, then format
      DISK_ID=$(hdiutil attach -nomount "$EFI_IMG" | head -n1 | awk '{print $1}')
      # Use the raw device for formatting (replace /dev/disk with /dev/rdisk)
      RAW_DISK=$(echo "$DISK_ID" | sed 's|/dev/disk|/dev/rdisk|')
      # Use FAT16 which works reliably with smaller sizes
      newfs_msdos -F 16 -v EFIBOOT "$RAW_DISK" >/dev/null 2>&1
      hdiutil detach "$DISK_ID" >/dev/null 2>&1
    else
      mkfs.fat -F 16 -n "EFIBOOT" "$EFI_IMG" >/dev/null
    fi
    
    echo "[*] Mounting ESP and copying EFI files..."
    # Mount the ESP image
    if [[ "$OSTYPE" == "darwin"* ]]; then
      hdiutil attach -mountpoint "$ESP_MOUNT" "$EFI_IMG" >/dev/null
      # Ensure clean state and copy EFI structure
      mkdir -p "$ESP_MOUNT/EFI/BOOT"
      cp -R "$SRC/EFI"/* "$ESP_MOUNT/EFI/"
      # Unmount ESP
      hdiutil detach "$ESP_MOUNT" >/dev/null
    else
      # Linux approach
      ESP_TEMP=$(mktemp -d)
      sudo mount -o loop "$EFI_IMG" "$ESP_TEMP"
      mkdir -p "$ESP_TEMP/EFI/BOOT"
      cp -R "$SRC/EFI"/* "$ESP_TEMP/EFI/"
      sudo umount "$ESP_TEMP"
      rmdir "$ESP_TEMP"
    fi
    
    # Create ISO root directory structure
    echo "[*] Preparing ISO root structure..."
    ISO_ROOT="$OUT/iso_root"
    rm -rf "$ISO_ROOT"
    mkdir -p "$ISO_ROOT"
    
    # Copy source files to ISO root
    cp -R "$SRC"/* "$ISO_ROOT/"
    
    # Place EFI boot image in proper location for xorriso
    mkdir -p "$ISO_ROOT/EFI/BOOT"
    cp "$EFI_IMG" "$ISO_ROOT/EFI/BOOT/efiboot.img"
    
    # Create hybrid ISO with proper EFI boot
    echo "[*] Creating bootable ISO with EFI System Partition..."
    xorriso -as mkisofs \
      -iso-level 3 \
      -full-iso9660-filenames \
      -volid "$VOL" \
      -eltorito-alt-boot \
      -e EFI/BOOT/efiboot.img \
      -no-emul-boot \
      -isohybrid-gpt-basdat \
      -o "$OUTISO" \
      "$ISO_ROOT"
    
    # Clean up temporary files
    rm -f "$EFI_IMG"
    rm -rf "$ISO_ROOT"
    
  elif [[ "$OSTYPE" == "darwin"* ]]; then
    echo "[*] Using hdiutil (may not be EFI bootable - consider installing xorriso)"
    TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
    cp -a "$SRC"/* "$TMP/"  # Copy contents, not the directory itself
    rm -f $OUTISO || true
    hdiutil makehybrid -iso -joliet -default-volume-name "$VOL" -o "$OUTISO" "$TMP"
  else
    echo "ERROR: xorriso required for EFI bootable ISO creation"; exit 1
  fi
}
# Normal OC ISO
build_iso "$EFI_BUILD" "$OUT/opencore.iso" "OC_BOOT"

echo "[*] ISO created at $OUT/opencore.iso"
