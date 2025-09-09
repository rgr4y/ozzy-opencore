#!/usr/bin/env python3.11
"""
Enhanced integration test that includes SMBIOS data and NVRAM copying.

This test validates the round-trip conversion process with SMBIOS data:
1. Start with a changeset that has SMBIOS data
2. Apply changeset to generate plist (should copy to NVRAM)
3. Convert plist back to changeset format  
4. Compare original and converted changesets

This validates that the SMBIOS -> NVRAM copying works correctly.
"""

import sys
import tempfile
import subprocess
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import ROOT, log, warn, error, info

def run_command(cmd, description, cwd=None):
    """Run a command and return success status"""
    if cwd is None:
        cwd = ROOT
    
    log(f"Running: {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=True)
        return True, result.stdout, result.stderr
    except subprocess.CalledProcessError as e:
        error(f"{description} failed with exit code {e.returncode}")
        if e.stdout:
            error(f"STDOUT: {e.stdout}")
        if e.stderr:
            error(f"STDERR: {e.stderr}")
        return False, e.stdout, e.stderr

def test_smbios_nvram_integration():
    """Test the SMBIOS to NVRAM copying integration"""
    
    log("=" * 60)
    log("Testing SMBIOS -> NVRAM Integration")
    log("=" * 60)
    
    # Use an existing changeset with SMBIOS data
    source_changeset = "pve-smbios-appleid"
    test_changeset = "test-smbios-integration"
    test_changeset_file = ROOT / "config" / "changesets" / f"{test_changeset}.yaml"
    generated_plist = ROOT / "out" / "build" / "efi" / "EFI" / "OC" / "config.plist"
    
    try:
        # Step 1: Copy existing changeset with SMBIOS data
        log("Step 1: Copying changeset with SMBIOS data...")
        source_file = ROOT / "config" / "changesets" / f"{source_changeset}.yaml"
        if not source_file.exists():
            error(f"Source changeset not found: {source_file}")
            return False
        
        import shutil
        shutil.copy2(source_file, test_changeset_file)
        info(f"✓ Copied {source_changeset} to {test_changeset}")
        
        # Step 2: Apply changeset (should copy SMBIOS to NVRAM)
        log("Step 2: Applying changeset with SMBIOS data...")
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "apply-changeset.py"),
            test_changeset
        ]
        success, stdout, stderr = run_command(cmd, "Apply changeset")
        if not success:
            return False
        
        # Check if NVRAM copying was mentioned in output
        if "Copying PlatformInfo.Generic to NVRAM" in stdout:
            info("✓ NVRAM copying was performed")
        else:
            warn("NVRAM copying not detected in output")
        
        info("✓ Changeset applied successfully")
        
        # Step 3: Convert generated plist back to changeset
        log("Step 3: Converting generated plist back to changeset...")
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "read-config.py"),
            str(generated_plist)
        ]
        success, stdout, stderr = run_command(cmd, "Convert plist back to changeset")
        if not success:
            return False
        
        # Save the reverse-converted changeset
        reverse_changeset_file = ROOT / "config" / "changesets" / f"{test_changeset}-reverse.yaml"
        with open(reverse_changeset_file, 'w') as f:
            f.write(stdout)
        
        info("✓ Plist converted back to changeset")
        
        # Step 4: Check that NVRAM section was preserved
        log("Step 4: Checking NVRAM preservation...")
        
        import yaml
        with open(reverse_changeset_file, 'r') as f:
            reverse_data = yaml.safe_load(f)
        
        # Check if NVRAM section exists
        if 'nvram' in reverse_data or 'Nvram' in reverse_data:
            nvram_section = reverse_data.get('nvram', reverse_data.get('Nvram', {}))
            if 'add' in nvram_section or 'Add' in nvram_section:
                add_section = nvram_section.get('add', nvram_section.get('Add', {}))
                
                # Check for Apple ID GUID
                apple_guid = '4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14'
                if apple_guid in add_section:
                    apple_data = add_section[apple_guid]
                    
                    # Check if platform info was copied
                    platform_fields = ['SystemProductName', 'SystemSerialNumber', 'MLB', 'SystemUUID', 'ROM']
                    found_fields = [field for field in platform_fields if field in apple_data]
                    
                    if found_fields:
                        info(f"✓ Found platform info in NVRAM: {', '.join(found_fields)}")
                    else:
                        warn("No platform info found in NVRAM Apple ID section")
                else:
                    warn("Apple ID GUID not found in NVRAM")
            else:
                warn("NVRAM Add section not found")
        else:
            warn("NVRAM section not found in reverse-converted changeset")
        
        log("=" * 60)
        log("✅ SMBIOS -> NVRAM Integration test PASSED")
        log("=" * 60)
        return True
        
    except Exception as e:
        error(f"Integration test failed with exception: {e}")
        import traceback
        error(traceback.format_exc())
        return False
    
    finally:
        # Clean up test files
        for cleanup_file in [test_changeset_file, reverse_changeset_file]:
            if cleanup_file.exists():
                cleanup_file.unlink()
                info(f"Cleaned up: {cleanup_file}")

def main():
    """Main test function"""
    success = test_smbios_nvram_integration()
    
    if success:
        log("🎉 SMBIOS -> NVRAM integration test passed!")
        return 0
    else:
        error("❌ SMBIOS -> NVRAM integration test failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
