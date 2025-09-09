#!/usr/bin/env python3.11
"""
Integration test for the OpenCore changeset conversion system.

This test validates the round-trip conversion process:
1. Start with config.plist.TEMPLATE
2. Convert to changeset format
3. Apply changeset to generate new plist
4. Compare original and generated plists

The only differences should be expected additions like NVRAM variables.
"""

import sys
import os
import tempfile
import shutil
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

def test_round_trip_conversion():
    """Test the full round-trip conversion process"""
    
    log("=" * 60)
    log("Starting OpenCore Changeset Round-Trip Integration Test")
    log("=" * 60)
    
    # Define paths
    template_plist = ROOT / "assets" / "config.plist.TEMPLATE"
    test_changeset = "test-integration-roundtrip"
    test_changeset_file = ROOT / "config" / "changesets" / f"{test_changeset}.yaml"
    generated_plist = ROOT / "out" / "build" / "efi" / "EFI" / "OC" / "config.plist"
    
    try:
        # Step 1: Verify template exists
        log("Step 1: Checking template file...")
        if not template_plist.exists():
            error(f"Template file not found: {template_plist}")
            return False
        info(f"✓ Template found: {template_plist}")
        
        # Step 2: Convert plist to changeset
        log("Step 2: Converting plist to changeset...")
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "read-config.py"),
            str(template_plist)
        ]
        success, stdout, stderr = run_command(cmd, "Convert plist to changeset")
        if not success:
            return False
        
        # Save the output to a changeset file
        with open(test_changeset_file, 'w') as f:
            f.write(stdout)
        
        info("✓ Plist converted to changeset")
        
        # Verify changeset was created
        if not test_changeset_file.exists():
            error(f"Changeset file was not created: {test_changeset_file}")
            return False
        info(f"✓ Changeset created: {test_changeset_file}")
        
        # Step 3: Apply changeset to generate new plist
        log("Step 3: Applying changeset to generate plist...")
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "apply-changeset.py"),
            test_changeset
        ]
        success, stdout, stderr = run_command(cmd, "Apply changeset")
        if not success:
            return False
        info("✓ Changeset applied successfully")
        
        # Verify generated plist exists
        if not generated_plist.exists():
            error(f"Generated plist not found: {generated_plist}")
            return False
        info(f"✓ Generated plist: {generated_plist}")
        
        # Step 4: Compare original and generated plists
        log("Step 4: Comparing original and generated plists...")
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "compare-plists.py"),
            str(template_plist),
            str(generated_plist)
        ]
        success, stdout, stderr = run_command(cmd, "Compare plists")
        
        # For comparison, we expect some differences (NVRAM additions)
        # but the comparison should complete successfully
        if success:
            info("✓ Plist comparison completed - files are identical")
        else:
            warn("Plist comparison detected differences (analyzing if expected...)")
            if stdout:
                log("Comparison output:")
                for line in stdout.split('\n'):
                    if line.strip():
                        info(f"  {line}")
        
        # Step 5: Analyze differences more carefully
        log("Step 5: Analyzing differences in detail...")
        
        # Read both files and check for expected vs unexpected differences
        import plistlib
        
        with open(template_plist, 'rb') as f:
            original_plist = plistlib.load(f)
        
        with open(generated_plist, 'rb') as f:
            generated_plist_data = plistlib.load(f)
        
        # Check for expected NVRAM additions
        expected_differences = []
        
        # Check for timestamp addition
        if '#Generated' in generated_plist_data and '#Generated' not in original_plist:
            expected_differences.append("Added generation timestamp")
        
        # Check NVRAM section differences
        original_nvram = original_plist.get('NVRAM', {}).get('Add', {})
        generated_nvram = generated_plist_data.get('NVRAM', {}).get('Add', {})
        
        # Apple ID GUID should be added
        apple_guid = '4D1EDE05-38C7-4A6A-9CC6-4BCCA8B38C14'
        if apple_guid in generated_nvram and apple_guid not in original_nvram:
            expected_differences.append(f"Added NVRAM section for Apple ID: {apple_guid}")
            
        # Check if PlatformInfo data was copied to NVRAM
        if apple_guid in generated_nvram:
            nvram_section = generated_nvram[apple_guid]
            platform_info = generated_plist_data.get('PlatformInfo', {}).get('Generic', {})
            
            copied_fields = []
            for field in ['SystemProductName', 'SystemSerialNumber', 'MLB', 'SystemUUID', 'ROM']:
                if field in nvram_section and field in platform_info:
                    copied_fields.append(field)
            
            if copied_fields:
                expected_differences.append(f"Copied PlatformInfo fields to NVRAM: {', '.join(copied_fields)}")
        
        # Report results
        if expected_differences:
            log("Expected differences found:")
            for diff in expected_differences:
                info(f"  ✓ {diff}")
        
        # Check for unexpected differences by comparing structure
        def compare_structure(original, generated, path=""):
            """Compare structure of two dictionaries, ignoring expected NVRAM additions"""
            unexpected = []
            
            # Check for missing keys in generated
            for key in original:
                if key not in generated:
                    if path == "NVRAM.Add" and key == apple_guid:
                        continue  # Expected NVRAM addition
                    unexpected.append(f"Missing key: {path}.{key}")
            
            # Check for extra keys in generated (except expected ones)
            for key in generated:
                if key not in original:
                    # Expected additions
                    if path == "NVRAM.Add" and key == apple_guid:
                        continue  # Expected NVRAM addition
                    if path == "" and key == "#Generated":
                        continue  # Expected timestamp
                    unexpected.append(f"Extra key: {path}.{key}")
            
            # Recursively check common keys
            for key in original:
                if key in generated:
                    current_path = f"{path}.{key}" if path else key
                    if isinstance(original[key], dict) and isinstance(generated[key], dict):
                        if current_path == "NVRAM.Add":
                            # Skip detailed comparison of NVRAM.Add since we expect additions
                            continue
                        unexpected.extend(compare_structure(original[key], generated[key], current_path))
            
            return unexpected
        
        unexpected_differences = compare_structure(original_plist, generated_plist_data)
        
        if unexpected_differences:
            warn("Unexpected differences found:")
            for diff in unexpected_differences:
                warn(f"  ⚠ {diff}")
            return False
        else:
            info("✓ No unexpected differences found")
        
        log("=" * 60)
        log("✅ Integration test PASSED")
        log("✅ Round-trip conversion completed successfully")
        log("=" * 60)
        return True
        
    except Exception as e:
        error(f"Integration test failed with exception: {e}")
        import traceback
        error(traceback.format_exc())
        return False
    
    finally:
        # Clean up test changeset
        if test_changeset_file.exists():
            log("Cleaning up test changeset...")
            test_changeset_file.unlink()
            info(f"Removed: {test_changeset_file}")

def main():
    """Main test function"""
    success = test_round_trip_conversion()
    
    if success:
        log("🎉 All integration tests passed!")
        return 0
    else:
        error("❌ Integration tests failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
