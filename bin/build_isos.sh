#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/out"; mkdir -p "$OUT"
BUILD="$OUT/build"
EFI_BUILD="$BUILD/efi"

build_iso() {
  local SRC="$1" ; local OUTISO="$2" ; local VOL="$3"
  if [[ "$OSTYPE" == "darwin"* ]]; then
    TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
    cp -a "$SRC"/* "$TMP/"  # Copy contents, not the directory itself
    rm -f $OUTISO || true
    hdiutil makehybrid -iso -joliet -default-volume-name "$VOL" -o "$OUTISO" "$TMP"
  else
    command -v xorriso >/dev/null 2>&1 || { echo "xorriso required on Linux"; exit 1; }
    xorriso -as mkisofs -R -J -V "$VOL" -o "$OUTISO" \
      -eltorito-alt-boot -e EFI/BOOT/BOOTx64.efi -no-emul-boot "$SRC"
  fi
}
# Normal OC ISO
build_iso "$EFI_BUILD" "$OUT/opencore.iso" "OC_BOOT"
# ResetNVRAM ISO
if [ -f "$EFI_BUILD/EFI/OC/Tools/ResetNvramEntry.efi" ]; then
  TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
  mkdir -p "$TMP/EFI/BOOT" "$TMP/EFI/OC"
  cp -a "$EFI_BUILD/EFI/OC"/* "$TMP/EFI/OC/"  # Copy contents
  cp -a "$EFI_BUILD/EFI/OC/Tools/ResetNvramEntry.efi" "$TMP/EFI/BOOT/BOOTx64.efi"
  build_iso "$TMP" "$OUT/opencore-resetnvram.iso" "OC_RESET"
else
  echo "[*] No ResetNvramEntry.efi; skipping reset ISO."
fi
echo "[*] ISOs at $OUT"
