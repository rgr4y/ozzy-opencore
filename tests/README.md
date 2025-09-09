# OpenCore Deployment System - Tests

This directory contains integration tests for the OpenCore deployment system.

## Available Tests

### test-conversion.py
**Round-trip Conversion Integration Test**

This test validates the complete round-trip conversion process:
1. Starts with `config.plist.TEMPLATE`
2. Converts to changeset format using `read-config.py`
3. Applies changeset to generate new plist using `apply-changeset.py`
4. Compares original and generated plists using `compare-plists.py`

**Expected Results:**
- Files should be nearly identical
- Only expected difference: generation timestamp (`#Generated`)
- No unexpected structural differences

### test-smbios-integration.py
**SMBIOS -> NVRAM Integration Test**

This test validates the SMBIOS to NVRAM copying functionality:
1. Uses an existing changeset with SMBIOS data
2. Applies changeset (should copy PlatformInfo.Generic to NVRAM)
3. Converts generated plist back to changeset format
4. Validates NVRAM copying was performed

**Expected Results:**
- NVRAM copying should be detected during application
- Generated config should contain SMBIOS data in both PlatformInfo and NVRAM sections

## Running Tests

### Run All Tests
```bash
python3 tests/run-tests.py
```

### Run Individual Tests
```bash
python3 tests/test-conversion.py
python3 tests/test-smbios-integration.py
```

## Test Philosophy

These integration tests validate the entire changeset system end-to-end:

1. **Data Integrity**: Ensure no data loss during conversions
2. **Format Consistency**: Verify proper format handling (hex strings, base64, etc.)
3. **Feature Validation**: Confirm SMBIOS copying and other features work correctly
4. **Regression Prevention**: Catch breaking changes early

## Adding New Tests

To add a new test:

1. Create a new test file in `tests/` directory
2. Follow the existing pattern with proper logging
3. Add the test to `run-tests.py`
4. Ensure cleanup of temporary files
5. Return 0 for success, 1 for failure

## Test Data

Tests use:
- `assets/config.plist.TEMPLATE` as the baseline configuration
- `config/changesets/pve-smbios-appleid.yaml` for SMBIOS testing
- Temporary files are automatically cleaned up after tests
