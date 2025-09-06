# macOS → Proxmox OpenCore Builder/Deployer (Sequoia, RX 580, NVMe/USB passthrough)

Run on **macOS**. Builds OpenCore EFI, patches `config.plist` declaratively, builds OC ISO(s),
then pushes to remote Proxmox via SSH and updates VM config. One-command deploy.

See `config/deploy.env.example` to set remote host/VMID/paths.

## Quick Start

1. **Setup on your Mac:**
   ```bash
   cd ~/Downloads
   unzip macos-oc-remote-deploy.zip -d ./macos-oc-remote-deploy
   cd macos-oc-remote-deploy
   ```

2. **Configure your Proxmox connection:**
   ```bash
   cp config/deploy.env.example config/deploy.env
   # Edit config/deploy.env with your Proxmox host details
   ```

3. **Fetch OpenCore + core kexts:**
   ```bash
   ./ozzy fetch
   ```

4. **Deploy to Proxmox:**
   ```bash
   # Deploy with the default Ryzen 3950X + RX 580 configuration
   ./ozzy proxmox --changeset ryzen3950x_rx580_AMDVanilla
   
   # Or just build the ISO without deploying
   ./ozzy proxmox --build-only
   
   # Check deployment status
   ./ozzy status
   ```

## SMBIOS Serial Generation

Before deploying, you need valid SMBIOS serial numbers for your Mac. You can generate these separately:

### Generate Serial Numbers

```bash
# List available changesets
./ozzy list

# Generate SMBIOS data for a specific changeset (only if placeholders detected)
./ozzy serial --changeset ryzen3950x_rx580_AMDVanilla

# Force generation of new SMBIOS data
./ozzy serial --changeset ryzen3950x_rx580_AMDVanilla --force
```

The script will:
- Check if `macserial` utility is available (fetched by `./ozzy fetch`)
- Generate new serial number, MLB, and UUID if placeholders are detected
- Update the changeset YAML file directly
- Create a backup of the original file

### USB EFI Creation

Create a USB-ready EFI structure for bare metal installation:

```bash
# Create USB EFI with automatic SMBIOS generation
./ozzy usb --changeset ryzen3950x_rx580_AMDVanilla

# Create USB EFI and deploy directly to USB drive
python3 scripts/create_usb_efi.py --changeset ryzen3950x_rx580_mac --usb /Volumes/MyUSB

# Skip SMBIOS generation if you already generated serials separately
python3 scripts/create_usb_efi.py --changeset ryzen3950x_rx580_mac --skip-smbios-generation

# Dry run to see what would be done
python3 scripts/create_usb_efi.py --changeset ryzen3950x_rx580_mac --dry-run
```

**Note:** The serial generation modifies your changeset YAML file. When you later apply the changeset with `apply_changeset.py`, it will use these generated serial numbers in the actual config.plist.

## Commands

### Using Ozzy (Recommended)

The `ozzy` script provides a unified interface for all operations:

```bash
# Show all available commands
./ozzy --help

# Apply a changeset
./ozzy apply ryzen3950x_rx580_AMDVanilla

# Create USB-ready EFI
./ozzy usb --changeset ryzen3950x_rx580_AMDVanilla --output ./usb

# Deploy to Proxmox
./ozzy proxmox --changeset ryzen3950x_rx580_AMDVanilla --rebuild

# Fetch OpenCore assets
./ozzy fetch

# Clean output directories  
./ozzy clean

# Generate SMBIOS data
./ozzy smbios ryzen3950x_rx580_AMDVanilla

# Generate serial numbers
./ozzy serial --changeset ryzen3950x_rx580_AMDVanilla --force

# Set up Python environment
./ozzy setupenv

# Show project status
./ozzy status

# List available changesets
./ozzy list
```

### Legacy Commands

- `./deploy --changeset <name>` - Apply changeset and deploy to Proxmox
- `./deploy --build-only` - Build OpenCore ISO without deploying  
- `./deploy --status` - Check deployment status and configuration
- `./deploy --rebuild` - Force rebuild of ISO before deployment
- `./deploy --help` - Show all available options

./bin/fetch_assets.sh

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
