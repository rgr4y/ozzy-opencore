#!/usr/bin/env python3
import plistlib

data = plistlib.load(open('efi-build/EFI/OC/config.plist', 'rb'))
drivers = data.get('UEFI', {}).get('Drivers', [])
target_drivers = ['HfsPlus.efi', 'OpenCanopy.efi', 'OpenRuntime.efi', 'ResetNvramEntry.efi', 'UsbMouseDxe.efi']

for target in target_drivers:
    count = drivers.count(target)
    if count > 1:
        print(f'{target}: {count} times (duplicate!)')
    else:
        print(f'{target}: {count} times')

print(f'\nTotal drivers: {len(drivers)}')
print(f'Last 10 drivers: {drivers[-10:]}')
