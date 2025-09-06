#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="$ROOT/efi-build/EFI/OC/config.plist"
OV="$ROOT/out/opencore/Utilities/ocvalidate/ocvalidate"
if [ ! -f "$OV" ]; then echo "ocvalidate not found at $OV"; exit 1; fi
echo "[*] Using ocvalidate: $OV"
"$OV" "$CFG" || true
