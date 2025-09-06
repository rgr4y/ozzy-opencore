#!/usr/bin/env python3.11
"""
Path Management Library for OpenCore Remote Deploy

Centralized path management for all build artifacts, work directories,
and output locations. All paths are organized under the 'out' directory
for better structure and easier cleanup.
"""

import os
from pathlib import Path
from typing import Optional


class PathManager:
    """Centralized path management for the OpenCore build system"""
    
    def __init__(self, root_dir: Optional[Path] = None):
        """Initialize path manager with project root directory"""
        if root_dir is None:
            # Auto-detect root directory (find the directory containing this file's parent)
            self.root = Path(__file__).resolve().parents[1]
        else:
            self.root = Path(root_dir).resolve()
        
        # Ensure out directory exists
        self.out.mkdir(exist_ok=True)
    
    @property
    def out(self) -> Path:
        """Base output directory - all build artifacts go here"""
        return self.root / "out"
    
    @property
    def config(self) -> Path:
        """Configuration directory"""
        return self.root / "config"
    
    @property
    def changesets(self) -> Path:
        """Changesets directory"""
        return self.config / "changesets"
    
    @property
    def scripts(self) -> Path:
        """Scripts directory"""
        return self.root / "scripts"
    
    @property
    def bin(self) -> Path:
        """Binary/shell scripts directory"""
        return self.root / "bin"
    
    @property
    def assets(self) -> Path:
        """Static assets directory"""
        return self.root / "assets"
    
    @property
    def lib(self) -> Path:
        """Library directory"""
        return self.root / "lib"
    
    # Build and work directories (organized under out/)
    
    @property
    def build_root(self) -> Path:
        """Main build directory - all build outputs"""
        return self.out / "build"
    
    @property
    def efi_build(self) -> Path:
        """EFI build directory - primary OpenCore build location"""
        return self.out / "build" / "efi"
    
    @property
    def usb_build(self) -> Path:
        """USB build directory"""
        return self.out / "usb"
    
    @property
    def iso_build(self) -> Path:
        """ISO build directory"""
        return self.out / "iso"
    
    @property
    def logs_dir(self) -> Path:
        """Build logs directory"""
        return self.out / "logs"
    
    # OpenCore specific paths
    
    @property
    def opencore_release(self) -> Path:
        """Downloaded OpenCore release directory"""
        return self.out / "opencore"
    
    @property
    def opencore_root(self) -> Path:
        """Alias for opencore_release"""
        return self.opencore_release
    
    @property
    def opencore_repo(self) -> Path:
        """OpenCore repository clone"""
        return self.out / "opencore-repo"
    
    @property
    def oc_efi(self) -> Path:
        """OpenCore EFI directory"""
        return self.efi_build / "EFI" / "OC"
    
    @property
    def oc_boot(self) -> Path:
        """OpenCore BOOT directory"""
        return self.efi_build / "EFI" / "BOOT"
    
    @property
    def oc_config(self) -> Path:
        """OpenCore config.plist file"""
        return self.oc_efi / "config.plist"
    
    @property
    def oc_drivers(self) -> Path:
        """OpenCore Drivers directory"""
        return self.oc_efi / "Drivers"
    
    @property
    def oc_kexts(self) -> Path:
        """OpenCore Kexts directory"""
        return self.oc_efi / "Kexts"
    
    @property
    def oc_tools(self) -> Path:
        """OpenCore Tools directory"""
        return self.oc_efi / "Tools"
    
    @property
    def oc_acpi(self) -> Path:
        """OpenCore ACPI directory"""
        return self.oc_efi / "ACPI"
    
    # Template and output files
    
    @property
    def efi_template(self) -> Path:
        """EFI template directory"""
        return self.root / "efi-template"
    
    @property
    def opencore_iso(self) -> Path:
        """Generated OpenCore ISO file"""
        return self.out / "opencore.iso"
    
    @property
    def reset_nvram_iso(self) -> Path:
        """Generated Reset NVRAM ISO file"""
        return self.out / "reset-nvram.iso"
    
    # USB specific paths
    
    @property
    def usb_efi(self) -> Path:
        """USB EFI directory"""
        return self.usb_build / "EFI"
    
    @property
    def usb_deployment_info(self) -> Path:
        """USB deployment info file"""
        return self.usb_build / "DEPLOYMENT_INFO.txt"
    
    # Tools and utilities
    
    @property
    def ocvalidate(self) -> Path:
        """OpenCore validation tool"""
        return self.opencore_release / "Utilities" / "ocvalidate" / "ocvalidate"
    
    @property
    def macserial(self) -> Path:
        """macserial tool for SMBIOS generation"""
        return self.opencore_release / "Utilities" / "macserial" / "macserial"
    
    @property
    def sample_plist(self) -> Path:
        """OpenCore sample config.plist"""
        return self.opencore_release / "Docs" / "Sample.plist"
    
    # Validation and temporary paths
    
    @property
    def validation_script(self) -> Path:
        """Validation shell script"""
        return self.scripts / "validate.sh"
    
    def temp_iso_dir(self, name: str = "temp_iso") -> Path:
        """Create and return a temporary ISO build directory"""
        temp_dir = self.build / name
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir
    
    def changeset_file(self, name: str) -> Path:
        """Get path to a specific changeset file"""
        if not name.endswith('.yaml'):
            name += '.yaml'
        return self.changesets / name
    
    def ensure_build_dirs(self):
        """Ensure all necessary build directories exist"""
        dirs_to_create = [
            self.build,
            self.efi_build,
            self.usb_build,
            self.iso_build,
            self.oc_efi,
            self.oc_boot,
            self.oc_drivers,
            self.oc_kexts,
            self.oc_tools,
            self.oc_acpi,
        ]
        
        for directory in dirs_to_create:
            directory.mkdir(parents=True, exist_ok=True)
    
    def clean_build_dirs(self):
        """Clean all build directories"""
        import shutil
        
        if self.build.exists():
            shutil.rmtree(self.build)
        
        # Remove ISOs
        for iso_file in [self.opencore_iso, self.reset_nvram_iso]:
            if iso_file.exists():
                iso_file.unlink()
    
    def get_legacy_path(self, legacy_name: str) -> Path:
        """
        Get the new path for a legacy path name
        Used for backward compatibility during transition
        """
        legacy_mapping = {
            'efi-build': self.efi_build,
            'usb-efi': self.usb_build,
            'EFI': self.oc_efi.parent,  # EFI parent directory
        }
        
        return legacy_mapping.get(legacy_name, self.root / legacy_name)
    
    def __str__(self) -> str:
        """String representation showing key paths"""
        return f"PathManager(root={self.root}, out={self.out})"
    
    def __repr__(self) -> str:
        return self.__str__()


# Global instance for easy access
paths = PathManager()


def get_paths(root_dir: Optional[Path] = None) -> PathManager:
    """Get a PathManager instance"""
    if root_dir is None:
        return paths
    return PathManager(root_dir)


# Convenience functions for common operations
def ensure_build_dirs():
    """Ensure all build directories exist"""
    paths.ensure_build_dirs()


def clean_build_dirs():
    """Clean all build directories"""
    paths.clean_build_dirs()


# Legacy compatibility functions (deprecated but available during transition)
def get_efi_build_path():
    """Get EFI build path (legacy compatibility)"""
    return paths.efi_build


def get_usb_efi_path():
    """Get USB EFI path (legacy compatibility)"""
    return paths.usb_build


def get_opencore_path():
    """Get OpenCore EFI path (legacy compatibility)"""
    return paths.oc_efi


if __name__ == "__main__":
    # Test the path manager
    print("OpenCore Path Manager")
    print("=" * 50)
    print(f"Root directory: {paths.root}")
    print(f"Output directory: {paths.out}")
    print(f"Build directory: {paths.build}")
    print(f"EFI build directory: {paths.efi_build}")
    print(f"USB build directory: {paths.usb_build}")
    print(f"OpenCore config: {paths.oc_config}")
    print(f"Sample plist: {paths.sample_plist}")
    print(f"ocvalidate tool: {paths.ocvalidate}")
    
    print("\nCreating build directories...")
    paths.ensure_build_dirs()
    print("Done!")
