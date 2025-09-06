#!/usr/bin/env python3
"""
Common utilities and helper functions for OpenCore deployment scripts.

This module provides shared functionality to reduce code duplication across
the various Python scripts in the project.
"""

import os
import sys
import subprocess
import shlex
import json
from pathlib import Path

# Project root directory
ROOT = Path(__file__).resolve().parents[1]

# Color constants for terminal output
class Colors:
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    BLUE = '\033[0;34m'
    NC = '\033[0m'  # No Color

def log(msg): print(f"{Colors.GREEN}[*]{Colors.NC} {msg}")
def warn(msg): print(f"{Colors.YELLOW}[!]{Colors.NC} {msg}")
def error(msg): print(f"{Colors.RED}[ERROR]{Colors.NC} {msg}")
def info(msg): print(f"{Colors.BLUE}[INFO]{Colors.NC} {msg}")

def load_config():
    """Load configuration from deploy.env file"""
    env_file = ROOT / 'config' / 'deploy.env'
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
            warn(f"Could not load {env_file}: {e}")
    else:
        warn(f"{env_file} not found, using defaults")

def run_command(cmd: str, description=None, check=True, capture_output=False):
    """Execute a local command with proper error handling"""
    if description:
        log(description)
    log(f"Running: {cmd}")
    
    try:
        if capture_output:
            result = subprocess.run(cmd, shell=True, check=check, capture_output=True, text=True, cwd=ROOT)
            return result
        else:
            result = subprocess.run(cmd, shell=True, check=check, cwd=ROOT)
            return result.returncode == 0
    except subprocess.CalledProcessError as e:
        error(f"Command failed with exit code {e.returncode}")
        if capture_output and e.stderr:
            error(f"Error output: {e.stderr}")
        return False if not capture_output else e
    except Exception as e:
        error(f"Command execution failed: {e}")
        return False if not capture_output else None

def run_legacy(cmd: str):
    """Legacy run function for backward compatibility"""
    print(f'[+] {cmd}')
    subprocess.check_call(cmd, shell=True, cwd=ROOT)

def get_remote_config():
    """Get remote connection configuration"""
    return {
        'host': os.getenv('PROXMOX_HOST', '10.0.1.10'),
        'user': os.getenv('PROXMOX_USER', 'root'),
        'vmid': os.getenv('PROXMOX_VMID', '100'),
        'workdir': os.getenv('PROXMOX_WORKDIR', '/root/workspace'),
        'installer_iso': os.getenv('PROXMOX_INSTALLER_ISO', 'Sequoia.iso')
    }

def scp(local: Path, remote: str):
    """Copy file to remote host"""
    config = get_remote_config()
    host = config['host']
    user = config['user']
    
    log(f'Copying {local} to {user}@{host}:{remote}')
    cmd = f'scp "{local}" {user}@{host}:"{remote}"'
    return run_command(cmd, check=True)

def ssh(cmd: str):
    """Execute command on remote host"""
    config = get_remote_config()
    host = config['host']
    user = config['user']
    
    log(f'SSH: {cmd}')
    # Use shlex.quote to properly escape the command for SSH
    escaped_cmd = shlex.quote(cmd)
    ssh_cmd = f"ssh {user}@{host} {escaped_cmd}"
    return run_command(ssh_cmd, check=True)

def ensure_directory(path: Path):
    """Ensure directory exists, create if necessary"""
    if not path.exists():
        log(f"Creating directory: {path}")
        path.mkdir(parents=True, exist_ok=True)
    return path

def read_json_file(file_path: Path):
    """Read and parse JSON file"""
    try:
        with open(file_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        error(f"Failed to read JSON file {file_path}: {e}")
        return None

def write_json_file(file_path: Path, data):
    """Write data to JSON file"""
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except Exception as e:
        error(f"Failed to write JSON file {file_path}: {e}")
        return False

def find_files_by_pattern(directory: Path, pattern: str):
    """Find files matching a glob pattern in directory"""
    if not directory.exists():
        return []
    return list(directory.glob(pattern))

def cleanup_macos_metadata(directory: Path):
    """Remove macOS metadata files recursively"""
    count = 0
    for root, dirs, files in os.walk(directory):
        # Remove ._* files
        for file in files[:]:  # Use slice copy to modify during iteration
            if file.startswith('._'):
                file_path = os.path.join(root, file)
                os.remove(file_path)
                count += 1
        # Remove __MACOSX directories
        for dir_name in dirs[:]:  # Use slice copy to modify during iteration
            if dir_name == '__MACOSX':
                dir_path = os.path.join(root, dir_name)
                import shutil
                shutil.rmtree(dir_path)
                count += 1
    
    if count > 0:
        log(f"Cleaned up {count} macOS metadata files")
    return count

def validate_file_exists(file_path: Path, description="File"):
    """Validate that a file exists, raise error if not"""
    if not file_path.exists():
        error(f"{description} not found: {file_path}")
        raise FileNotFoundError(f"{description} not found: {file_path}")
    return file_path

def get_project_paths():
    """Get commonly used project paths"""
    return {
        'root': ROOT,
        'config': ROOT / 'config',
        'changesets': ROOT / 'config' / 'changesets',
        'scripts': ROOT / 'scripts',
        'assets': ROOT / 'assets',
        'out': ROOT / 'out',
        'efi_build': ROOT / 'efi-build',
        'efi_oc': ROOT / 'efi-build' / 'EFI' / 'OC',
        'usb_efi': ROOT / 'usb-efi',
        'deploy_env': ROOT / 'config' / 'deploy.env',
        'sources_json': ROOT / 'config' / 'sources.json',
    }

def check_required_tools(tools):
    """Check if required command-line tools are available"""
    missing = []
    for tool in tools:
        try:
            subprocess.run(['which', tool], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            missing.append(tool)
    
    if missing:
        error(f"Missing required tools: {', '.join(missing)}")
        return False
    return True

def get_changeset_path(changeset_name: str):
    """Get the full path to a changeset file"""
    paths = get_project_paths()
    
    # Handle both with and without .yaml extension
    if not changeset_name.endswith('.yaml'):
        changeset_name += '.yaml'
    
    changeset_path = paths['changesets'] / changeset_name
    return changeset_path

def list_available_changesets():
    """List all available changeset files"""
    paths = get_project_paths()
    if not paths['changesets'].exists():
        return []
    
    changesets = list(paths['changesets'].glob('*.yaml'))
    return [cs.stem for cs in sorted(changesets)]
