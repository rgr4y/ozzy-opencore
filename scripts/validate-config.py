#!/usr/bin/env python3.11
"""
Validate OpenCore Configuration

This script validates the OpenCore config.plist using ocvalidate.
Returns exit code 0 if valid, 1 if invalid or validation failed.
"""

import sys
import subprocess
import argparse
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import ROOT, log, warn, error, info, run_command, paths, validate_file_exists

def validate_config(config_path=None):
    """Validate OpenCore configuration using ocvalidate"""
    
    # Determine config path
    if config_path:
        config_file = Path(config_path)
    else:
        config_file = paths.oc_efi / 'config.plist'
    
    if not config_file.exists():
        error(f"Config file not found: {config_file}")
        return False
    
    # Find ocvalidate
    ocvalidate_path = paths.opencore_root / "Utilities" / "ocvalidate" / "ocvalidate"
    if not ocvalidate_path.exists():
        error("ocvalidate not found")
        error(f"Expected at: {ocvalidate_path}")
        error("Please run './ozzy fetch' first to download OpenCore tools")
        return False
    
    log(f"Validating config: {config_file}")
    log(f"Using ocvalidate: {ocvalidate_path}")
    
    # Run validation
    try:
        result = subprocess.run(
            [str(ocvalidate_path), str(config_file)],
            capture_output=True,
            text=True,
            cwd=ROOT
        )
        
        # Print output
        if result.stdout:
            print(result.stdout.strip())
        if result.stderr:
            print(result.stderr.strip())
        
        if result.returncode == 0:
            log("✓ Configuration is valid")
            return True
        else:
            error("✗ Configuration validation failed")
            return False
            
    except Exception as e:
        error(f"Validation failed: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description='Validate OpenCore configuration')
    parser.add_argument('config', nargs='?', help='Path to config.plist (default: current EFI config)')
    parser.add_argument('--quiet', '-q', action='store_true', help='Only show errors')
    
    args = parser.parse_args()
    
    try:
        if validate_config(args.config):
            if not args.quiet:
                info("Configuration validation passed")
            return 0
        else:
            return 1
    except KeyboardInterrupt:
        warn("Validation cancelled by user")
        return 1
    except Exception as e:
        error(f"Validation failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
