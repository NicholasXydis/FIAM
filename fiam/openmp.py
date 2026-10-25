# OpenMP for LightGBM on a fresh machine, kit copy loaded first (B9).

import ctypes
import ctypes.util
import platform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / "models" / "openmp"
LIBRARY = {"mac": "libomp.dylib", "linux": "libgomp.so.1"}
# Where the Mac wheel looks; a library there needs no preload.
MAC_PLACES = ("/opt/homebrew/opt/libomp/lib/libomp.dylib", "/opt/local/lib/libomp/libomp.dylib")


# This machine as the kit names it, such as mac-arm64 or linux-x64.
def machine() -> str:
    system = {"Darwin": "mac", "Linux": "linux", "Windows": "windows"}.get(platform.system(), "")
    chip = "arm64" if platform.machine().lower() in ("arm64", "aarch64") else "x64"
    return f"{system}-{chip}"


# True when the system already has the runtime LightGBM looks for.
def system_has(name: str) -> bool:
    if name.startswith("mac"):
        return any(Path(p).exists() for p in MAC_PLACES)
    return ctypes.util.find_library("gomp") is not None


# Loads the kit's runtime before LightGBM when the system lacks it.
def preload(kit: Path = KIT) -> str:
    name = machine()
    family = name.split("-")[0]
    if family not in LIBRARY:
        return "not needed"
    if system_has(name):
        return "system"
    path = kit / name / LIBRARY[family]
    if not path.exists():
        return "missing"
    ctypes.CDLL(str(path), mode=ctypes.RTLD_GLOBAL)
    return "kit"
