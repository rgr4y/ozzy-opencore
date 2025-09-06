# OpenCore Changeset Configuration Guide

## Overview

A changeset is a YAML configuration file that defines modifications to apply to an OpenCore configuration. It uses a declarative approach where you specify only the changes you want to make, rather than editing the entire config.plist file manually.

## File Structure

Changesets are stored in changesets and use the `.yaml` extension. The system applies these changes to a base OpenCore template to generate the final configuration.

## Changeset Sections

### 1. Kernel Extensions (kexts)

```yaml
kexts:
  - { bundle: "Lilu.kext", exec: "Lilu" }
  - { bundle: "VirtualSMC.kext", exec: "VirtualSMC" }
  - { bundle: "WhateverGreen.kext", exec: "WhateverGreen" }
  - { bundle: "AppleMCEReporterDisabler.kext", exec: "" }
```

**Purpose**: Defines kernel extensions to load
**Fields**:
- `bundle`: The .kext directory name
- `exec`: The executable file inside Contents/MacOS/ (empty string if no executable)

### 2. Booter Quirks

```yaml
booter_quirks:
  AvoidRuntimeDefrag: True
  EnableSafeModeSlide: True
  ProvideCustomSlide: True
  SetupVirtualMap: False
```

**Purpose**: Controls low-level boot behavior and memory management
**Common Settings**:
- `AvoidRuntimeDefrag`: Prevents memory fragmentation issues
- `EnableSafeModeSlide`: Enables KASLR in safe mode
- `ProvideCustomSlide`: Provides custom KASLR values
- `SetupVirtualMap`: Maps EFI runtime services (disable for newer systems)

### 3. Kernel Quirks

```yaml
kernel_quirks:
  DisableLinkeditJettison: True
  ForceSecureBootScheme: True
  ProvideCurrentCpuInfo: True
  XhciPortLimit: False
```

**Purpose**: Modifies kernel behavior and patches
**Common Settings**:
- `DisableLinkeditJettison`: Required when using Lilu
- `ForceSecureBootScheme`: Enables secure boot compatibility
- `ProvideCurrentCpuInfo`: Provides CPU info to macOS
- `XhciPortLimit`: Removes 15-port USB limit (usually false on newer macOS)

### 4. Boot Arguments

```yaml
boot_args: "keepsyms=1 debug=0x100"
```

**Purpose**: Kernel command line arguments
**Common Arguments**:
- `keepsyms=1`: Keep kernel symbols for debugging
- `debug=0x100`: Enable debug output
- `npci=0x2000`: Fix PCI configuration issues
- `agdpmod=pikera`: Fix AMD GPU issues

### 5. System Integrity Protection (SIP)

```yaml
csr_active_config: "00000000"
```

**Purpose**: Controls macOS System Integrity Protection
**Values**:
- `"00000000"`: SIP fully enabled (most secure)
- `"03000000"`: SIP partially disabled
- `"67000000"`: SIP mostly disabled (less secure)

### 6. Security Settings

```yaml
secureboot_model: "Disabled"
vault: "Optional"
scan_policy: 0
```

**Purpose**: Controls OpenCore security features
**Settings**:
- `secureboot_model`: "Disabled", "Default", or specific model
- `vault`: "Optional", "Basic", or "Secure"
- `scan_policy`: 0 (scan all) or bitmask for specific drives

### 7. Tools and Utilities

```yaml
tools:
  - { Name: "UEFI Shell", Path: "OpenShell.efi", Enabled: True, Auxiliary: True }
  - { Name: "Reset NVRAM", Path: "ResetNvramEntry.efi", Enabled: True, Auxiliary: True }
```

**Purpose**: Adds utilities to OpenCore boot menu
**Fields**:
- `Name`: Display name in boot menu
- `Path`: EFI file name in Tools directory
- `Enabled`: Whether to load the tool
- `Auxiliary`: Hide unless ShowPicker is enabled

### 8. ACPI Tables

```yaml
acpi_add:
  - "SSDT-EC-USBX.aml"
  - "SSDT-AWAC.aml"

acpi_quirks:
  ResetLogoStatus: True
  NormalizeHeaders: False
```

**Purpose**: Custom ACPI tables and ACPI behavior modification
**acpi_add**: List of .aml files to inject
**acpi_quirks**: ACPI-related system fixes

### 9. Device Properties

```yaml
device_properties:
  PciRoot(0x0)/Pci(0x1F,0x3):
    layout-id: [1, 0, 0, 0]
  PciRoot(0x0)/Pci(0x2,0x0):
    AAPL,ig-platform-id: [0, 0, 26, 9]
```

**Purpose**: Injects properties into specific PCI devices
**Format**: PCI path → property dictionary
**Data Types**: Arrays represent binary data (Data type in plist)

### 10. UEFI Drivers

```yaml
uefi_drivers:
  - path: "HfsPlus.efi"
    enabled: true
    load_early: false
    arguments: ""
    comment: "HFS+ filesystem support"
```

**Purpose**: Loads UEFI drivers for filesystem support, etc.
**Fields**:
- `path`: Driver filename in Drivers directory
- `enabled`: Whether to load the driver
- `load_early`: Load before other drivers
- `arguments`: Command line arguments for driver

### 11. SMBIOS Information

```yaml
smbios:
  SystemProductName: "MacPro7,1"
  SystemSerialNumber: "F5KFV03CP7QM"
  MLB: "F5K124100J9K3F7JA"
  SystemUUID: "CE35AC97-8B7E-452A-A2AB-A5907F81DA12"
  ROM: [220, 55, 20, 97, 202, 80]
```

**Purpose**: System identification for macOS compatibility
**Fields**:
- `SystemProductName`: Mac model (MacPro7,1, iMac19,1, etc.)
- `SystemSerialNumber`: Unique serial number
- `MLB`: Main Logic Board serial
- `SystemUUID`: System UUID
- `ROM`: MAC address as byte array

## Hardware-Specific Examples

### AMD Ryzen Systems
```yaml
booter_quirks:
  SetupVirtualMap: False  # Important for AMD
kernel_quirks:
  ProvideCurrentCpuInfo: True  # Required for AMD
```

### Intel Systems
```yaml
booter_quirks:
  SetupVirtualMap: True   # Usually needed for Intel
kernel_quirks:
  AppleXcpmCfgLock: True  # If CFG-Lock can't be disabled
```

### NVIDIA Graphics
```yaml
boot_args: "keepsyms=1 nvda_drv_vrl=1"
# Note: NVIDIA support limited to older macOS versions
```

### AMD Graphics
```yaml
boot_args: "keepsyms=1 agdpmod=pikera"
kexts:
  - { bundle: "WhateverGreen.kext", exec: "WhateverGreen" }
```

## Usage Workflow

1. **Create changeset**: Write YAML file with desired modifications
2. **Apply changeset**: `.apply_changeset.py config/changesets/my_config.yaml`
3. **Validate**: validate.sh to check for errors
4. **Test**: Boot and verify functionality
5. **Deploy**: `./deploy --changeset my_config` for remote deployment

## Best Practices

1. **Start minimal**: Begin with basic kexts and gradually add features
2. **One change at a time**: Make incremental modifications for easier debugging
3. **Hardware-specific**: Research your specific hardware requirements
4. **Validate frequently**: Run validation after each change
5. **Backup working configs**: Keep copies of working changesets
6. **Use real serials**: Generate valid SMBIOS data for your target Mac model

## Common Troubleshooting

- **Validation errors**: Check data types (arrays for binary data, proper boolean values)
- **Boot failures**: Start with minimal kexts, add one at a time
- **USB issues**: Ensure proper USB mapping kexts for your motherboard
- **Graphics issues**: Verify correct device properties for your GPU
- **Audio issues**: Check layout-id values for your audio codec

This declarative approach makes OpenCore configuration more maintainable and allows for easy hardware-specific variants while maintaining a clean base template.