#!/usr/bin/env python3.11
import sys, argparse, yaml, json, shutil, base64
from pathlib import Path
import subprocess

# Add lib directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'lib'))
from paths import paths

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, bytes):
            return list(obj)
        return super().default(obj)

def convert_data_values(obj):
    """Convert data values to proper format for plist handling"""
    if isinstance(obj, dict):
        result = {}
        for key, value in obj.items():
            if key == 'built-in' and isinstance(value, list):
                # Convert integer array to bytes for built-in property
                result[key] = bytes(value)
            elif key == 'ROM' and isinstance(value, list):
                # Convert integer array to bytes for ROM
                result[key] = bytes(value)
            elif isinstance(value, str) and key == 'ROM':
                # Handle hex string conversion for ROM
                try:
                    # Remove any spaces and convert hex to bytes
                    hex_str = value.replace(' ', '')
                    result[key] = bytes.fromhex(hex_str)
                except ValueError:
                    result[key] = value
            else:
                result[key] = convert_data_values(value)
        return result
    elif isinstance(obj, list):
        return [convert_data_values(item) for item in obj]
    else:
        return obj

ROOT = paths.root
EFI = paths.oc_efi
# Use clean OpenCore Sample.plist instead of problematic SampleCustom.plist
TEMPLATE = paths.sample_plist
PATCHER = paths.scripts / "patch_plist.py"

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("changeset"); ap.add_argument("--dry-run", action="store_true")
    a=ap.parse_args()

    assert TEMPLATE.exists(), f"Missing template {TEMPLATE}"
    
    # Ensure build directories exist
    paths.ensure_build_dirs()
    
    shutil.copy2(TEMPLATE, paths.oc_config)

    cs=yaml.safe_load(open(a.changeset))
    ops=[]
    
    # Clear all existing arrays to start fresh (important for Sample.plist which has examples)
    ops.append({"op":"clear","path":["UEFI","Drivers"]})
    ops.append({"op":"clear","path":["UEFI","ReservedMemory"]})
    ops.append({"op":"clear","path":["Kernel","Add"]})
    ops.append({"op":"clear","path":["Kernel","Block"]})
    ops.append({"op":"clear","path":["Kernel","Patch"]})
    ops.append({"op":"clear","path":["ACPI","Add"]})
    ops.append({"op":"clear","path":["ACPI","Delete"]})
    ops.append({"op":"clear","path":["ACPI","Patch"]})
    ops.append({"op":"clear","path":["Misc","Tools"]})
    ops.append({"op":"clear","path":["Misc","Entries"]})
    ops.append({"op":"clear","path":["Booter","MmioWhitelist"]})
    ops.append({"op":"clear","path":["Booter","Patch"]})
    
    for k in cs.get("kexts", []):
        entry = {
            "Arch":"x86_64","BundlePath":k["bundle"],"Enabled":True,
            "MinKernel":"20.0.0","MaxKernel":"",
            "PlistPath":"Contents/Info.plist",
            "Comment":f"Essential kext: {k['bundle']}"
        }
        # Set ExecutablePath - empty string for plist-only kexts, full path for others
        if k.get("exec", "").strip():
            entry["ExecutablePath"] = "Contents/MacOS/" + k["exec"]
        else:
            entry["ExecutablePath"] = ""
        ops.append({"op":"append","path":["Kernel","Add"],"key":"BundlePath","entry":entry})
    if "booter_quirks" in cs: ops.append({"op":"merge","path":["Booter","Quirks"],"entries":cs["booter_quirks"]})
    if "kernel_quirks" in cs: ops.append({"op":"merge","path":["Kernel","Quirks"],"entries":cs["kernel_quirks"]})
    if "kernel_emulate" in cs: ops.append({"op":"merge","path":["Kernel","Emulate"],"entries":cs["kernel_emulate"]})
    if "acpi_quirks" in cs: ops.append({"op":"merge","path":["ACPI","Quirks"],"entries":cs["acpi_quirks"]})
    if "misc_boot" in cs: ops.append({"op":"merge","path":["Misc","Boot"],"entries":cs["misc_boot"]})
    if "device_properties" in cs: ops.append({"op":"merge","path":["DeviceProperties","Add"],"entries":convert_data_values(cs["device_properties"])})
    if "boot_args" in cs: ops.append({"op":"set","path":["NVRAM","Add","7C436110-AB2A-4BBB-A880-FE41995C9F82","boot-args"],"value":cs["boot_args"]})
    if "csr_active_config" in cs:
        val=bytes.fromhex(cs["csr_active_config"])
        ops.append({"op":"set","path":["NVRAM","Add","7C436110-AB2A-4BBB-A880-FE41995C9F82","csr-active-config"],"value":val})
    for key in ["secureboot_model","vault","scan_policy"]:
        if key in cs:
            m={"secureboot_model":"SecureBootModel","vault":"Vault","scan_policy":"ScanPolicy"}[key]
            ops.append({"op":"merge","path":["Misc","Security"],"entries":{m: cs[key]}})
    for tool in cs.get("tools", []): 
        entry = {
            "Name": tool.get("Name", ""),
            "Path": tool.get("Path", ""),
            "Enabled": tool.get("Enabled", True),
            "Auxiliary": tool.get("Auxiliary", True),
            "Arguments": tool.get("Arguments", ""),
            "Comment": tool.get("Comment", ""),
            "Flavour": tool.get("Flavour", "Auto"),
            "FullNvramAccess": tool.get("FullNvramAccess", False),
            "RealPath": tool.get("RealPath", False),
            "TextMode": tool.get("TextMode", False)
        }
        ops.append({"op":"append","path":["Misc","Tools"],"key":"Path","entry":entry})
    for aml in cs.get("acpi_add", []): ops.append({"op":"append","path":["ACPI","Add"],"key":"Path","entry":{"Enabled":True,"Path":aml,"Comment":f"Custom ACPI: {aml}"}})
    
    # Handle UEFI drivers with proper structure
    for drv in cs.get("uefi_drivers", []):
        if isinstance(drv, str):
            # Legacy string format
            ops.append({"op":"append","path":["UEFI","Drivers"],"entry":drv})
        elif isinstance(drv, dict):
            # New dict format
            entry = {
                "Path": drv.get("path", ""),
                "Enabled": drv.get("enabled", True),
                "LoadEarly": drv.get("load_early", False),
                "Arguments": drv.get("arguments", ""),
                "Comment": drv.get("comment", "")
            }
            ops.append({"op":"append","path":["UEFI","Drivers"],"key":"Path","entry":entry})
    if "smbios" in cs: ops.append({"op":"merge","path":["PlatformInfo","Generic"],"entries":convert_data_values(cs["smbios"])})

    if a.dry_run: print(json.dumps(ops, indent=2, cls=CustomJSONEncoder)); return
    subprocess.check_call([str(PATCHER), str(paths.oc_config), json.dumps(ops, cls=CustomJSONEncoder)])
    print("[*] Patched config.plist")
if __name__=="__main__": main()
