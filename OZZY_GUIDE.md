# Ozzy Master Script - Usage Guide

## Overview

The `ozzy` script is the unified command interface for the macOS OpenCore Remote Deploy project. It provides a simple, consistent way to run all operations without having to remember different script paths or worry about Python dependencies.

## How to Use Changesets

Changesets are YAML configuration files that define OpenCore settings declaratively. Instead of manually editing `config.plist` files, you describe what you want and the system applies those changes.

### Understanding Changesets

1. **Location**: Changesets are stored in `config/changesets/` with `.yaml` extension
2. **Format**: YAML files with structured sections for different OpenCore components
3. **Application**: Use `ozzy apply <changeset>` to generate the final OpenCore configuration

### AMD Vanilla Changeset Applied

You've successfully applied the AMD Vanilla changeset which includes:

- **Kexts**: Essential drivers (Lilu, WhateverGreen, VirtualSMC, AppleMCEReporterDisabler)
- **Booter Quirks**: Memory management settings optimized for AMD systems
- **Kernel Quirks**: CPU detection and power management for AMD processors
- **Boot Args**: Debug flags and AMD GPU patches (`agdpmod=pikera`)
- **ACPI**: Required SSDT tables for USB and power management
- **SMBIOS**: iMacPro1,1 profile suitable for high-end AMD systems

### Key Changes for AMD Systems

The applied changeset makes several AMD-specific optimizations:

1. **SetupVirtualMap: false** - Critical for X570 and newer AMD boards
2. **DummyPowerManagement: true** - Required for AMD CPU power management
3. **ProvideCurrentCpuInfo: true** - Ensures proper CPU detection
4. **agdpmod=pikera** - Fixes compatibility with modern AMD GPUs

## Quick Reference

```bash
# Essential workflow
./ozzy fetch                                    # Download OpenCore assets
./ozzy apply ryzen3950x_rx580_AMDVanilla       # Apply your changeset
./ozzy serial --changeset ryzen3950x_rx580_AMDVanilla --force  # Generate unique serials
./ozzy usb --changeset ryzen3950x_rx580_AMDVanilla            # Create USB installer
./ozzy proxmox --changeset ryzen3950x_rx580_AMDVanilla        # Deploy to VM

# Maintenance
./ozzy status                                   # Check project status
./ozzy list                                     # List available changesets
./ozzy clean                                    # Clean build outputs
./ozzy setupenv                                 # Fix Python environment
```

## Next Steps

1. **Generate Unique Serial Numbers**: Use `./ozzy serial --changeset ryzen3950x_rx580_AMDVanilla --force` to create unique SMBIOS data
2. **Test the Configuration**: Use `./ozzy usb` to create a bootable USB for testing
3. **Deploy to Proxmox**: Use `./ozzy proxmox` for virtualized testing
4. **Customize Further**: Modify the changeset file to add your specific hardware requirements

The changeset approach makes it easy to version control your OpenCore configurations and share them across different builds while maintaining the flexibility to customize for specific hardware configurations.
