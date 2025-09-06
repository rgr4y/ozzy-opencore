# Assets Directory

This directory contains assets required for deployment, such as GPU BIOS ROM files.

## GPU BIOS ROM Files

Place your GPU BIOS ROM files here for PCIe passthrough. For example:

- `RX580.rom` - MSI Armor RX 580 4G OC GOP-enabled BIOS ROM
- `RX6800XT.rom` - AMD RX 6800 XT BIOS ROM
- `RTX3080.rom` - NVIDIA RTX 3080 BIOS ROM (with UEFI GOP support)

## ROM File Requirements

For macOS compatibility:
1. ROM must have UEFI GOP (Graphics Output Protocol) support
2. ROM should be extracted from the exact GPU model you're using
3. File size typically 256KB (262,144 bytes) for modern GPUs

## Extraction Tools

- **GPU-Z**: Can save BIOS ROM on Windows
- **nvflash**: NVIDIA GPU BIOS tool
- **atiflash/amdvbflash**: AMD GPU BIOS tool

## Usage

The deployment script will automatically upload ROM files specified in changesets:

```yaml
proxmox_vm:
  assets:
    - src: "./assets/RX580.rom"
      dest: "/usr/share/kvm/RX580.rom"
      mode: "0644"
```
