#!/usr/bin/env python3.11
"""
Switch Changeset Workflow

Easily switch between changesets for testing. Shows what will change,
applies the changeset, validates it, and provides feedback.
"""

import sys
import subprocess
import argparse
from pathlib import Path

# Import our common libraries
sys.path.insert(0, str(Path(__file__).parent.parent))
from lib import ROOT, log, warn, error, info, run_command, list_available_changesets

def switch_changeset(changeset_name, force=False):
    """Switch to a different changeset with validation and feedback"""
    
    log(f"Switching to changeset: {changeset_name}")
    
    # Check if changeset exists
    changeset_path = ROOT / "config" / "changesets" / f"{changeset_name}.yaml"
    if not changeset_path.exists():
        error(f"Changeset not found: {changeset_path}")
        
        # Show available changesets
        available = list_available_changesets()
        if available:
            info("Available changesets:")
            for cs in sorted(available):
                info(f"  - {cs}")
        return False
    
    # Show what the changeset contains (summary)
    log("Changeset summary:")
    try:
        import yaml
        with open(changeset_path, 'r') as f:
            changeset_data = yaml.safe_load(f)
        
        if 'metadata' in changeset_data:
            metadata = changeset_data['metadata']
            if 'name' in metadata:
                info(f"  Name: {metadata['name']}")
            if 'description' in metadata:
                info(f"  Description: {metadata['description']}")
            if 'hardware' in metadata:
                hw = metadata['hardware']
                if 'cpu' in hw:
                    info(f"  CPU: {hw['cpu']}")
                if 'gpu' in hw:
                    info(f"  GPU: {hw['gpu']}")
        
        # Show main sections
        if 'opencore' in changeset_data:
            oc_data = changeset_data['opencore']
            sections = list(oc_data.keys())
            info(f"  OpenCore sections: {', '.join(sections)}")
        
    except Exception as e:
        warn(f"Could not read changeset details: {e}")
    
    # Ask for confirmation if not forced
    if not force:
        try:
            response = input("\nProceed with applying this changeset? [y/N]: ")
            if response.lower() not in ['y', 'yes']:
                info("Operation cancelled")
                return False
        except KeyboardInterrupt:
            info("\nOperation cancelled")
            return False
    
    # Apply the changeset
    log("Applying changeset...")
    apply_script = ROOT / "scripts" / "apply-changeset.py"
    cmd = [sys.executable, str(apply_script), str(changeset_path)]
    
    try:
        result = subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
        log("✓ Changeset applied successfully")
        
        # Show any output from the apply process
        if result.stdout:
            print(result.stdout)
            
    except subprocess.CalledProcessError as e:
        error(f"Failed to apply changeset: {e}")
        if e.stderr:
            print(e.stderr)
        return False
    
    # Show current status
    log("Current configuration status:")
    config_file = ROOT / "out" / "build" / "efi" / "EFI" / "OC" / "config.plist"
    if config_file.exists():
        info(f"✓ Config file: {config_file}")
    else:
        warn(f"✗ Config file not found: {config_file}")
    
    log("🎉 Changeset switch completed successfully!")
    info(f"You can now build ISO/USB with: ./ozzy build-iso or ./ozzy build-usb")
    
    return True

def main():
    parser = argparse.ArgumentParser(
        description='Switch Changeset: Easy changeset switching for testing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
This workflow helps you easily switch between changesets for testing:
1. Shows changeset details and what will change
2. Applies the changeset with validation
3. Provides feedback on current status

Example:
  python3 switch-changeset.py myconfig
  python3 switch-changeset.py testconfig --force
        """
    )
    parser.add_argument('changeset', help='Changeset name (without .yaml extension)')
    parser.add_argument('--force', '-f', action='store_true', help='Skip confirmation prompt')
    parser.add_argument('--list', '-l', action='store_true', help='List available changesets')
    
    args = parser.parse_args()
    
    if args.list:
        changesets = list_available_changesets()
        if changesets:
            log("Available changesets:")
            for cs in sorted(changesets):
                info(f"  - {cs}")
        else:
            warn("No changesets found")
        return 0
    
    try:
        if switch_changeset(args.changeset, args.force):
            return 0
        else:
            return 1
    except KeyboardInterrupt:
        warn("Operation cancelled by user")
        return 1
    except Exception as e:
        error(f"Switch failed: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
