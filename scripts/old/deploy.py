#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import shlex
from pathlib import Path

# Add lib directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from paths import paths

def load_config():
    """Load configuration from deploy.env file"""
    env_file = paths.config / 'deploy.env'
    if env_file.exists():
        try:
            with open(env_file, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        # Remove quotes if present
                        value = value.strip('"\'')
                        os.environ[key.strip()] = value
        except Exception as e:
            print(f"[!] Warning: Could not load {env_file}: {e}")
    else:
        print(f"[!] Warning: {env_file} not found, using defaults")

def run(cmd: str):
    """Execute a local command"""
    print(f'[+] {cmd}')
    subprocess.check_call(cmd, shell=True)

def scp(local: Path, remote: str):
    """Copy file to remote host"""
    host = os.getenv('PROXMOX_HOST', '10.0.1.10')
    user = os.getenv('PROXMOX_USER', 'root')
    print(f'[+] Copying {local} to {user}@{host}:{remote}')
    run(f'scp "{local}" {user}@{host}:"{remote}"')

def ssh(cmd: str):
    """Execute command on remote host"""
    host = os.getenv('PROXMOX_HOST', '10.0.1.10')
    user = os.getenv('PROXMOX_USER', 'root')
    print(f'[+] SSH: {cmd}')
    # Use shlex.quote to properly escape the command for SSH
    escaped_cmd = shlex.quote(cmd)
    run(f"ssh {user}@{host} {escaped_cmd}")

def build_opencore_iso(force_rebuild=False):
    """Build the OpenCore ISO using the build script"""
    print("[*] Building OpenCore ISO...")
    
    # Check if we need to clean first
    if force_rebuild:
        if paths.out.exists():
            print("[*] Cleaning previous build...")
            run(f'rm -rf "{paths.out}"/*')
    
    build_script = paths.bin / 'build_isos.sh'
    if not build_script.exists():
        raise SystemExit(f'Build script not found at {build_script}')
    
    # Make sure the script is executable
    run(f'chmod +x "{build_script}"')
    
    # Run the build script
    os.chdir(paths.root)
    run(f'bash "{build_script}"')

def deploy_to_proxmox(changeset_name=None, force_rebuild=False):
    """Deploy OpenCore configuration to Proxmox VM"""
    
    # Load environment configuration
    load_config()
    
    # If rebuilding, fetch assets first if they don't exist
    if force_rebuild:
        if not paths.ocvalidate.exists():
            print("[*] Fetching OpenCore assets for rebuild...")
            fetch_script = paths.bin / "fetch_assets.sh"
            if fetch_script.exists():
                run(f'bash "{fetch_script}"')
            else:
                print("[!] ERROR: fetch_assets.sh not found")
                raise SystemExit("Cannot fetch assets for rebuild")
    else:
        # Check that OpenCore assets are available for validation (only for non-rebuild)
        if not paths.ocvalidate.exists():
            print("[!] ERROR: OpenCore tools not found")
            print(f"[!] Expected ocvalidate at: {paths.ocvalidate}")
            print("[!] Please run './bin/fetch_assets.sh' first to download OpenCore")
            print("[!] Or use --rebuild to fetch assets automatically")
            raise SystemExit("OpenCore tools required for deployment")
    
    vmid = os.getenv('PROXMOX_VMID', '100')
    workdir = os.getenv('PROXMOX_WORKDIR', '/root/workspace')
    installer_iso = os.getenv('PROXMOX_INSTALLER_ISO', 'Sequoia.iso')
    
    print(f"[*] Deploying to VM {vmid} on Proxmox")
    
    # Apply changeset if specified
    changeset_data = None
    if changeset_name:
        changeset_file = paths.changeset_file(changeset_name)
        if not changeset_file.exists():
            raise SystemExit(f'Changeset not found: {changeset_file}')
        
        # Load changeset data for Proxmox configuration
        import yaml
        with open(changeset_file, 'r') as f:
            changeset_data = yaml.safe_load(f)
        
        print(f"[*] Applying changeset: {changeset_name}")
        # Use the same Python interpreter that's running this script
        cmd = [sys.executable, str(paths.scripts / "apply_changeset.py"), str(changeset_file)]
        print(f'[+] {" ".join(cmd)}')
        subprocess.check_call(cmd)
        
        # Validate the configuration (required for deployment)
        if paths.ocvalidate.exists():
            print("[*] Validating OpenCore configuration...")
            run(f'bash "{paths.validation_script}"')
        else:
            print("[!] ERROR: ocvalidate not found - cannot validate configuration")
            print(f"[!] Expected at: {paths.ocvalidate}")
            print("[!] Run './bin/fetch_assets.sh' first to download OpenCore tools")
            raise SystemExit("Validation required for deployment but ocvalidate not available")
    
    # Build or check for existing ISO
    if force_rebuild or not paths.opencore_iso.exists():
        build_opencore_iso(force_rebuild)
    
    if not paths.opencore_iso.exists():
        raise SystemExit(f'OpenCore ISO not found at {paths.opencore_iso}')
    
    print(f"[*] Using OpenCore ISO: {paths.opencore_iso}")
    
    # Upload ISO to Proxmox
    print("[*] Uploading OpenCore ISO to Proxmox...")
    scp(paths.opencore_iso, f'{workdir}/')
    
    # Copy ISO to Proxmox ISO storage
    iso_name = paths.opencore_iso.name
    print("[*] Installing ISO to Proxmox storage...")
    ssh(f"cp {workdir}/{iso_name} /var/lib/vz/template/iso/{iso_name}")
    
    # Stop VM if running (must be done before configuration changes)
    print(f"[*] Stopping VM {vmid}...")
    ssh(f"qm stop {vmid} || true")
    ssh(f"sleep 3")  # Give VM time to stop completely
    
    # Process Proxmox VM configuration from changeset
    if changeset_data and 'proxmox_vm' in changeset_data:
        proxmox_config = changeset_data['proxmox_vm']
        print("[*] Processing Proxmox VM configuration from changeset...")
        
        # Upload assets (like GPU BIOS ROM files)
        if 'assets' in proxmox_config:
            for asset in proxmox_config['assets']:
                src_relative = asset['src']
                dest_path = asset['dest']
                mode = asset.get('mode', '0644')
                
                # Handle relative paths properly
                if src_relative.startswith('./'):
                    src_path = paths.root / src_relative[2:]  # Remove "./" prefix
                else:
                    src_path = paths.root / src_relative
                
                if src_path.exists():
                    print(f"[*] Uploading asset: {src_path} -> {dest_path}")
                    # Upload to workdir first
                    scp(src_path, f'{workdir}/')
                    # Move to final destination and set permissions
                    ssh(f"mv {workdir}/{src_path.name} {dest_path}")
                    ssh(f"chmod {mode} {dest_path}")
                    print(f"[✓] Asset deployed: {dest_path} (mode: {mode})")
                else:
                    print(f"[!] ERROR: Asset not found: {src_path}")
                    print(f"[!] Expected ROM file at: {src_path}")
                    print(f"[!] Please ensure your GPU BIOS ROM file is placed in the assets directory")
                    raise SystemExit(f"Required asset missing: {src_path}")
        
        # Apply VM configuration overrides (VM must be stopped first)
        if 'conf_overrides' in proxmox_config:
            vm_id = proxmox_config.get('vmid', vmid)
            print(f"[*] Applying VM configuration overrides for VM {vm_id}...")
            
            for key, value in proxmox_config['conf_overrides'].items():
                print(f"[+] Setting {key} = {value}")
                ssh(f"qm set {vm_id} -{key} '{value}'")
            
            # Skip legacy config upload when changeset is used
            print("[*] Changeset configuration applied, skipping legacy VM config upload")
        else:
            # Check if VM config exists and upload it (legacy support)
            vm_config = paths.root / 'proxmox' / f'{vmid}.conf'
            if vm_config.exists():
                print(f"[*] Uploading legacy VM configuration: {vm_config}")
                scp(vm_config, f'/etc/pve/qemu-server/{vmid}.conf')
            else:
                print(f"[!] VM config not found at {vm_config}, skipping upload")
    else:
        # No changeset, try legacy config
        vm_config = paths.root / 'proxmox' / f'{vmid}.conf'
        if vm_config.exists():
            print(f"[*] Uploading legacy VM configuration: {vm_config}")
            scp(vm_config, f'/etc/pve/qemu-server/{vmid}.conf')
        else:
            print(f"[!] VM config not found at {vm_config}, skipping upload")
    
    # Configure VM storage (unless overridden by changeset)
    configure_storage = True
    if changeset_data and 'proxmox_vm' in changeset_data:
        proxmox_config = changeset_data['proxmox_vm']
        if 'conf_overrides' in proxmox_config:
            # Check if IDE configuration is handled by changeset
            overrides = proxmox_config['conf_overrides']
            if any(key.startswith('ide') for key in overrides.keys()):
                print("[*] IDE configuration handled by changeset, skipping default storage setup")
                configure_storage = False
    
    if configure_storage:
        print("[*] Configuring VM storage...")
        ssh(f"qm set {vmid} -ide0 local:iso/{iso_name},media=disk,cache=unsafe,size=10M")
        ssh(f"qm set {vmid} -ide2 local:iso/{installer_iso},cache=unsafe")
    
    # Start VM
    print(f"[*] Starting VM {vmid}...")
    ssh(f"qm start {vmid}")
    
    print(f"[✓] Deployment complete! VM {vmid} should now be booting with OpenCore")
    print(f"[i] You can access the VM console via Proxmox web interface")

def check_status():
    """Check the status of the deployment environment"""
    load_config()
    
    vmid = os.getenv('PROXMOX_VMID', '100')
    host = os.getenv('PROXMOX_HOST', '10.0.1.10')
    user = os.getenv('PROXMOX_USER', 'root')
    
    print(f"[*] Deployment Status")
    print(f"    Proxmox Host: {host}")
    print(f"    VM ID: {vmid}")
    print(f"    User: {user}")
    
    # Check local files
    iso_path = ROOT / 'out' / 'opencore.iso'
    config_path = ROOT / 'efi-build' / 'EFI' / 'OC' / 'config.plist'
    
    print(f"\n[*] Local Files:")
    print(f"    OpenCore ISO: {'✓' if iso_path.exists() else '✗'} {iso_path}")
    print(f"    Config.plist: {'✓' if config_path.exists() else '✗'} {config_path}")
    
    # Check changesets
    changesets_dir = ROOT / 'config' / 'changesets'
    if changesets_dir.exists():
        changesets = list(changesets_dir.glob('*.yaml'))
        print(f"\n[*] Available Changesets:")
        for cs in changesets:
            print(f"    - {cs.stem}")
    
    # Try to check VM status on Proxmox (if accessible)
    try:
        print(f"\n[*] Proxmox VM Status:")
        result = subprocess.run(f"ssh -o ConnectTimeout=5 {user}@{host} 'qm status {vmid}'", 
                              shell=True, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            print(f"    VM {vmid}: {result.stdout.strip()}")
        else:
            print(f"    Could not check VM status: {result.stderr.strip()}")
    except (subprocess.TimeoutExpired, Exception) as e:
        print(f"    Cannot connect to Proxmox: {e}")

def main():
    parser = argparse.ArgumentParser(description='Deploy OpenCore configuration to Proxmox VM')
    parser.add_argument('--changeset', '-c', help='Apply a specific changeset before deployment')
    parser.add_argument('--rebuild', '-r', action='store_true', help='Force rebuild of OpenCore ISO')
    parser.add_argument('--build-only', '-b', action='store_true', help='Only build the ISO, do not deploy')
    parser.add_argument('--status', '-s', action='store_true', help='Check deployment status')
    
    args = parser.parse_args()
    
    if args.status:
        check_status()
        return
    
    if args.build_only:
        print("[*] Building OpenCore ISO only...")
        
        # Apply changeset if specified
        if args.changeset:
            changeset_file = ROOT / 'config' / 'changesets' / f'{args.changeset}.yaml'
            if not changeset_file.exists():
                raise SystemExit(f'Changeset not found: {changeset_file}')
            
            print(f"[*] Applying changeset: {args.changeset}")
            # Use the same Python interpreter that's running this script
            cmd = [sys.executable, str(ROOT / "scripts" / "apply_changeset.py"), str(changeset_file)]
            print(f'[+] {" ".join(cmd)}')
            subprocess.check_call(cmd)
            
            # Validate the configuration (only if ocvalidate exists)
            validate_script = ROOT / "scripts" / "validate.sh"
            ocvalidate_path = ROOT / "out" / "opencore" / "Utilities" / "ocvalidate" / "ocvalidate"
            if ocvalidate_path.exists():
                print("[*] Validating OpenCore configuration...")
                run(f'bash "{validate_script}"')
            else:
                print("[*] Skipping validation (ocvalidate not available)")
        
        build_opencore_iso(args.rebuild)
        print("[✓] Build complete!")
        return
    
    try:
        deploy_to_proxmox(args.changeset, args.rebuild)
    except KeyboardInterrupt:
        print("\n[!] Deployment cancelled by user")
    except Exception as e:
        print(f"[!] Deployment failed: {e}")
        raise SystemExit(1)

if __name__ == '__main__':
    main()
