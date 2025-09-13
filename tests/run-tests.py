#!/usr/bin/env python3.11
"""
Test runner for OpenCore deployment system.

Runs all available tests and provides a summary.
"""

import sys
import subprocess
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import ROOT, log, warn, error, info

def run_test(test_path, description):
    """Run a single test and return success status"""
    log(f"Running {description}...")
    
    try:
        result = subprocess.run(
            [sys.executable, str(test_path)], 
            cwd=ROOT, 
            capture_output=True, 
            text=True, 
            check=True
        )
        info(f"✅ {description} PASSED")
        return True
    except subprocess.CalledProcessError as e:
        error(f"❌ {description} FAILED")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False

def main():
    """Run all tests"""
    log("=" * 60)
    log("OpenCore Deployment System - Test Suite")
    log("=" * 60)
    
    tests = [
        (ROOT / "tests" / "test-conversion.py", "Integration Test - Round-trip Conversion"),
        (ROOT / "tests" / "test-smbios-integration.py", "Integration Test - SMBIOS -> NVRAM"),
    ]
    
    passed = 0
    failed = 0
    
    for test_path, description in tests:
        if not test_path.exists():
            error(f"Test file not found: {test_path}")
            failed += 1
            break
        if run_test(test_path, description):
            passed += 1
        else:
            failed += 1
            # Fail fast to avoid cascading errors that obscure the root cause
            break
    
    log("=" * 60)
    log(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        log("🎉 All tests passed!")
        return 0
    else:
        error(f"❌ {failed} test(s) failed!")
        return 1

if __name__ == "__main__":
    sys.exit(main())
