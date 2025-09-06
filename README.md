# Ozzy - OpenCore Automation & Deployment System

**Modern, declarative OpenCore configuration for AMD Ryzen hackintosh systems**

Run on **macOS**. Builds OpenCore EFI configurations declaratively from YAML changesets, manages kext dependencies with DEBUG/RELEASE build support, generates bootable ISOs, creates USB installers, and optionally deploys to remote Proxmox VMs via SSH.

## Features

- 🚀 **Declarative Configuration**: Define OpenCore settings in YAML instead of manually editing config.plist
- 🔧 **AMD Vanilla Support**: Automatic core count detection and kernel patches for AMD Ryzen systems
- 📦 **Smart Kext Management**: Automatic download from GitHub releases with DEBUG/RELEASE build selection
- 🛡️ **Security & Debug Ready**: Full support for SecureBootModel, comprehensive debug logging, and NVRAM configuration
- 🔄 **Multi-Deployment**: Create USB installers, ISOs, or deploy directly to Proxmox VMs
- ✅ **Validation Built-in**: Automatic OpenCore configuration validation with detailed error reporting
- 🎯 **Hardware Optimized**: Pre-configured for Ryzen 9 3950X + RX 580 systems with Sequoia support

## Quick Start

1. **Clone and setup:**
   ```bash
   git clone git@github.com:rgr4y/ozzy-opencore.git
   cd ozzy-opencore
   ```

2. **Configure Proxmox connection (optional):**
   ```bash
   cp config/deploy.env.example config/deploy.env
   # Edit config/deploy.env with your Proxmox host details
   ```

3. **Fetch OpenCore + kexts:**
   ```bash
   ./ozzy fetch
   ```

4. **Deploy:**
   ```bash
   # Apply configuration and create USB EFI
   ./ozzy full-usb ryzen3950x_rx580_AMDVanilla
   
   # Or deploy to Proxmox VM
   ./ozzy proxmox --changeset ryzen3950x_rx580_AMDVanilla
   
   # Or just apply the changeset
   ./ozzy apply ryzen3950x_rx580_AMDVanilla
   ```

## Hardware Configuration

### Tested Hardware
- **CPU**: AMD Ryzen 9 3950X (16-core, auto-detected)
- **GPU**: AMD Radeon RX 580 8GB
- **Target OS**: macOS Sequoia (15.0+)
- **OpenCore**: Version 1.0.5
- **SMBIOS**: iMacPro1,1

### Included Kexts
The system automatically downloads and manages these kexts:

- **Lilu.kext** (RELEASE) - Kernel extension patching framework
- **NVMeFix.kext** (DEBUG) - NVMe power management and compatibility 
- **VirtualSMC.kext** (RELEASE) - SMC emulation for hardware monitoring
- **WhateverGreen.kext** (RELEASE) - GPU acceleration and display fixes
- **RestrictEvents.kext** (RELEASE) - Memory and CPU name fixes
- **AppleALC.kext** (RELEASE) - Audio codec support

### Debug & Security Features
- **Comprehensive Debug Logging**: Target=67, SysReport enabled, panic logs captured
- **Security**: SecureBootModel=Default, Vault=Optional, proper NVRAM configuration
- **AMD Optimizations**: 25 kernel patches with automatic core count detection
- **GPU**: agdpmod=pikera for optimal RX 580 performance

## SMBIOS Serial Generation

Before deploying, you need valid SMBIOS serial numbers. The system can generate these automatically:

### Generate Serial Numbers

```bash
# Generate SMBIOS data for a changeset (automatic detection of placeholders)
./ozzy serial --changeset ryzen3950x_rx580_AMDVanilla

# Force generation of new SMBIOS data
./ozzy serial --changeset ryzen3950x_rx580_AMDVanilla --force

# Generate with specific model (advanced usage)
./ozzy smbios ryzen3950x_rx580_AMDVanilla
```

The script automatically:
- Detects if valid serial numbers are already present
- Uses `macserial` utility from OpenCore releases
- Generates serial number, MLB, and UUID for iMacPro1,1
- Updates the changeset YAML file with generated values
- Creates a backup of the original changeset file

## Changesets & Configuration

### Understanding Changesets

Changesets are YAML files that declaratively define your OpenCore configuration:

```bash
# List available changesets
./ozzy list

# View changeset details
cat config/changesets/ryzen3950x_rx580_AMDVanilla.yaml

# Apply a changeset (generates config.plist)
./ozzy apply ryzen3950x_rx580_AMDVanilla

# Validate applied configuration
./ozzy validate
```

### AMD Vanilla Features

The `ryzen3950x_rx580_AMDVanilla` changeset includes:

- **25 AMD Kernel Patches**: Automatic CPU compatibility for Ryzen systems
- **16-Core Detection**: Auto-configures core count patches for Ryzen 9 3950X
- **RX 580 Optimization**: GPU patches and boot arguments for optimal performance
- **Power Management**: Proper ACPI tables and USB configuration
- **Debug Ready**: Comprehensive logging for troubleshooting
- **Sequoia Compatible**: Tested with macOS 15.0+

## Deployment Options

### USB EFI Creation

Create a USB-ready EFI structure for bare metal installation:

```bash
# Full workflow: apply changeset + create USB EFI
./ozzy full-usb ryzen3950x_rx580_AMDVanilla

# Create USB EFI with custom output directory  
./ozzy usb --changeset ryzen3950x_rx580_AMDVanilla --output ./my-efi

# Advanced: Deploy directly to mounted USB drive
python3 workflows/full-usb.py ryzen3950x_rx580_AMDVanilla --output /Volumes/EFI
```

### ISO Creation

Build bootable OpenCore ISOs:

```bash
# Build ISO from current configuration
./ozzy iso

# Build ISO with specific changeset
python3 scripts/build-iso.py --changeset ryzen3950x_rx580_AMDVanilla
```

### Proxmox Deployment

Deploy to remote Proxmox VMs (requires SSH key setup):

```bash
# Full deployment to Proxmox VM
./ozzy proxmox --changeset ryzen3950x_rx580_AMDVanilla

# Build only (no deployment)
./ozzy proxmox --build-only

# Check deployment status
./ozzy status
```

## Command Reference

### Ozzy Master Script

The `ozzy` script provides a unified interface for all operations:

```bash
# Core Operations
./ozzy fetch                    # Download OpenCore + kexts
./ozzy apply <changeset>        # Apply changeset to generate config.plist
./ozzy serial --changeset <changeset>  # Generate SMBIOS serial numbers
./ozzy validate                 # Validate current OpenCore configuration

# Build & Deploy
./ozzy full-usb <changeset>     # Complete USB workflow
./ozzy usb --changeset <changeset>  # Create USB EFI structure
./ozzy iso                      # Build OpenCore ISO
./ozzy proxmox --changeset <changeset>  # Deploy to Proxmox VM

# Utilities
./ozzy list                     # List available changesets
./ozzy clean                    # Clean output directories
./ozzy status                   # Show project status
./ozzy setupenv                 # Set up Python environment
./ozzy --help                   # Show all commands
```

### Advanced Operations

```bash
# Kext Management
python3 scripts/fetch-assets.py  # Download kexts with DEBUG/RELEASE selection

# Direct Changeset Application
python3 scripts/apply-changeset.py <changeset> --dry-run  # Preview changes
python3 scripts/apply-changeset.py <changeset>           # Apply changes

# Build Workflows
python3 workflows/full-usb.py <changeset> --force       # Force rebuild USB
python3 workflows/switch-changeset.py <old> <new>       # Switch configurations

# Configuration Management
python3 scripts/validate-config.py    # Validate OpenCore config
python3 scripts/read-config.py        # Read current config details
```

## Project Structure

```
ozzy-opencore/
├── ozzy                        # Master script - unified interface
├── scripts/                    # Core Python scripts
│   ├── fetch-assets.py        # Download OpenCore + kexts (was bin/fetch_assets.sh)
│   ├── apply-changeset.py     # Apply YAML changesets to config.plist
│   ├── build-iso.py           # Create bootable OpenCore ISOs
│   ├── generate-serial.py     # Generate SMBIOS serial numbers
│   └── validate-config.py     # Validate OpenCore configurations
├── workflows/                  # Multi-step automation workflows
│   ├── full-usb.py            # Complete USB creation workflow
│   ├── switch-changeset.py    # Switch between configurations
│   └── full-deploy.py         # Complete deployment workflow
├── config/                     # Configuration files
│   ├── sources.json           # Kext sources and build types
│   ├── deploy.env.example     # Proxmox deployment settings
│   └── changesets/            # OpenCore configuration changesets
│       └── ryzen3950x_rx580_AMDVanilla.yaml
├── lib/                        # Core Python libraries
│   ├── changeset.py           # Changeset processing logic
│   ├── deployment.py          # Deployment utilities
│   └── smbios.py              # SMBIOS generation
├── efi-template/               # Base OpenCore EFI structure
└── out/                        # Build outputs and cache
    ├── efi/                   # Generated EFI structure
    ├── kext-cache/            # Downloaded kext archives
    ├── kext-debug-*/          # DEBUG build kext extractions
    └── kext-release-*/        # RELEASE build kext extractions
```

## Technical Details

### Kext Build Type Support

The system supports both DEBUG and RELEASE builds of kexts:

```json
// config/sources.json
{
  "kexts": [
    {
      "name": "Lilu.kext",
      "repo": "acidanthera/Lilu"
      // Defaults to RELEASE build
    },
    {
      "name": "NVMeFix.kext", 
      "repo": "acidanthera/NVMeFix",
      "build_type": "DEBUG"  // Explicitly request DEBUG build
    }
  ]
}
```

### AMD Vanilla Integration

Automatic AMD kernel patch management:
- Downloads latest patches from AMD-OSX/AMD_Vanilla repository
- Applies 25 kernel patches for full AMD compatibility
- Auto-detects CPU core count (16 cores for Ryzen 9 3950X)
- Handles core count patches dynamically across macOS versions

### Validation & Security

- **OpenCore Validation**: Uses official `ocvalidate` tool for configuration verification
- **Security Model**: SecureBootModel=Default with proper signed kext validation
- **NVRAM Support**: Complete NVRAM configuration for Sequoia compatibility
- **Debug Logging**: Comprehensive Target=67 debug configuration for troubleshooting

### Deployment Flexibility

- **Local USB**: Create bootable USB installers for bare metal
- **ISO Creation**: Generate OpenCore ISOs for VM deployment
- **Remote Proxmox**: SSH-based deployment to Proxmox VE systems
- **Hot-swapping**: Switch between configurations without rebuilding assets

## Troubleshooting

### Common Issues

**Permission denied on ocvalidate:**
```bash
chmod +x out/opencore/Utilities/ocvalidate/ocvalidate
```

**Kext not found during USB creation:**
```bash
# Re-fetch assets to ensure kexts are available
./ozzy fetch
# Check kext directories
ls -la out/kext-*
```

**Invalid SMBIOS serials:**
```bash
# Force regenerate serial numbers
./ozzy serial --changeset ryzen3950x_rx580_AMDVanilla --force
```

**Debug verbose boot:**
The changeset includes comprehensive debug settings:
- `boot-args`: `-v debug=0x100 keepsyms=1`
- Debug Target: `0x43` (67 decimal) for full logging
- Panic logging enabled for crash analysis

### Getting Help

1. Check the validation output: `./ozzy validate`
2. Review debug logs in verbose boot mode
3. Verify hardware compatibility with included changeset
4. Consult the [OZZY_GUIDE.md](OZZY_GUIDE.md) for detailed changeset explanations

## License

This project is open source. Use at your own risk for educational purposes.

## Common Usages

./scripts/fetch-assets.py

Patch your OpenCore config from a declarative change-set (dry-run first):

./scripts/apply_changeset.py config/changesets/ryzen3950x_rx580_mac.yaml --dry-run
./scripts/apply_changeset.py config/changesets/ryzen3950x_rx580_mac.yaml

Validate (macOS binary from the OC release):

./scripts/validate.sh

Build the ISOs (macOS hdiutil; Linux fallback uses xorriso):

./bin/build_isos.sh

# creates:

# out/opencore.iso (normal OC)

# out/opencore-resetnvram.iso (boots ResetNvramEntry.efi directly)

One-command push to Proxmox and boot:

# normal flow

./bin/deploy.sh

# or if you want a one-time NVRAM wipe first:

./bin/deploy.sh --nvram-reset

What deploy does:

SCP out/opencore.iso → /var/lib/vz/template/iso/opencore-osx-proxmox-vm.iso

(if --nvram-reset) also SCP reset ISO → /var/lib/vz/template/iso/opencore-resetnvram.iso

Copy vm/100.conf → /etc/pve/qemu-server/100.conf (atomic replace)

Ensures installer line exists: ide2: local:iso/macOS-Sequoia-15.4.iso,cache=unsafe

If --nvram-reset: start VM with the reset ISO for ~12s, stop, swap back to OC ISO, start again

Otherwise: start VM with OC ISO directly

Notes mapped to your constraints

No sudo (Proxmox runs as root). All remote commands assume key-based SSH for root@10.0.1.10.

Single source of truth: config/deploy.env holds REMOTE_SSH_HOST, REMOTE_VM_ID, ISO store path, names.

Installer ISO is assumed present at /var/lib/vz/template/iso/macOS-Sequoia-15.4.iso (matches your conf).

NVRAM reset option: uses a special ISO where BOOTx64.efi == ResetNvramEntry.efi. Deploy does a quick boot with it, then switches back to the normal OC ISO—no manual picker step.

Your baseline config.plist: used as the starting template (from your upload). The change-set only adds the minimal Sequoia/RX580 deltas; doesn’t fight your existing structure.

Validation rules respected: csr-active-config is 4-byte data; DisableLinkeditJettison=True when Lilu is present; OpenRuntime.efi ensured when ProvideCustomSlide=True; paths are short/ASCII-safe.

Edit points you’ll tweak most

config/deploy.env – remote host, VMID, ISO names.

config/changesets/ryzen3950x_rx580_mac.yaml – toggle SMBIOS, boot-args, add/remove kexts/tools/quirks.

vm/100.conf – the Proxmox VM template; deploy replaces /etc/pve/qemu-server/100.conf with this.

Sanity vs. your 100.conf

Leaves your passthrough lines untouched (0b:00.{0,1}, 03:00.0, 07:00.3).

Keeps vga: none, q35, ovmf, agent:1, balloon:0.

CPU line is still Penryn,vendor=GenuineIntel,+aes per your file. If you want to switch to -cpu Haswell-noTSX,... style via args:, I can add a small templater to flip this declaratively.
