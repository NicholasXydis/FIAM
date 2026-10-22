# The data inventory and rebuild comparisons; standard library only.

import json
import sys
from pathlib import Path

from _shared import ROOT, fingerprint, stamp

DATA = ROOT / "data"
INVENTORY = DATA / "INVENTORY.json"
USB_GB = 61.0
# Each source's data folder and its licence note.
SOURCES = {
    "organisers": ("organisers", "competition use only, never redistributed"),
    "bundle": ("fiam_v1", "derived from organisers' files and WRDS; private"),
    "edgar": ("edgar", "SEC public data, fair-access rules followed"),
    "noaa": ("noaa", "US government public domain (NOAA NCEI)"),
    "stock": ("v4/extracts", "WRDS via McGill; private, derived extracts only"),
    "carbon": ("carbon_arc", "derived results only, credit Carbon Arc; raw never public"),
    "amazon": ("amazon", "UCSD Amazon Reviews 2023; research use, summaries only"),
}
# Kept on the Mac only: the nightly bulk file and scratch folders.
OFF_USB = ("edgar/submissions.zip", "amazon/raw", "amazon/tmp")


# Files under a folder as relative path to size, skipping part files.
def files(folder: Path) -> dict[str, int]:
    if not folder.exists():
        return {}
    found = (p for p in folder.rglob("*") if p.is_file() and not p.name.endswith(".part"))
    return {p.relative_to(folder).as_posix(): p.stat().st_size for p in found}


# True when a path inside data/ stays on the Mac rather than the USB.
def stays_home(relative: str) -> bool:
    return any(relative == part or relative.startswith(part + "/") for part in OFF_USB)


# Writes data/INVENTORY.json and prints each source with its USB size.
def status() -> int:
    report, kit = {"made_at": stamp(), "sources": {}}, 0
    for name, (folder, licence) in SOURCES.items():
        found = files(DATA / folder)
        usb = sum(s for f, s in found.items() if not stays_home(f"{folder}/{f}"))
        kit += usb
        report["sources"][name] = {"folder": folder, "licence": licence, "files": len(found)}
        report["sources"][name] |= {"bytes": sum(found.values()), "usb_bytes": usb}
        print(
            f"{name:11} {len(found):7,} files {sum(found.values()) / 1e9:7.2f} GB  "
            f"on USB {usb / 1e9:6.2f} GB  {licence}"
        )
    organisers = DATA / "organisers"
    report["organisers_sha256"] = {f: fingerprint(organisers / f) for f in files(organisers)}
    report["usb_data_gb"] = round(kit / 1e9, 2)
    INVENTORY.write_text(json.dumps(report, indent=1), encoding="utf-8")
    size = f"{kit / 1e9:.1f} GB of {USB_GB:.0f} usable"
    print(f"Data on the USB: {size}, before models and installers")
    print(f"Inventory written to {INVENTORY}")
    return 0


# Receipts and logs differ on every run because they record times.
def bookkeeping(name: str) -> bool:
    leaf = name.rsplit("/", 1)[-1]
    return leaf in ("receipts.json", "manifest.json", "log.jsonl") or leaf.endswith(".receipt.json")


# A rebuilt folder against ours: same, changed, new and missing files.
def compare(rebuilt: Path, ours: Path) -> int:
    new = {f: s for f, s in files(rebuilt).items() if not bookkeeping(f)}
    old = {f: s for f, s in files(ours).items() if not bookkeeping(f)}
    same = [f for f in new if f in old and fingerprint(rebuilt / f) == fingerprint(ours / f)]
    changed = [f for f in new if f in old and f not in same]
    added, missing = [f for f in new if f not in old], [f for f in old if f not in new]
    print(f"rebuild vs ours: {len(same)} same, {len(changed)} changed, {len(added)} new")
    for label, names in (("changed", changed), ("new", added)):
        for f in names[:10]:
            print(f"  {label}: {f}")
    print(f"  ({len(missing)} of ours not in this rebuild; receipts and logs not compared)")
    return 0


# status, or compare <rebuilt folder> <our folder>.
if __name__ == "__main__":
    verb, rest = (sys.argv[1] if len(sys.argv) > 1 else ""), sys.argv[2:]
    if verb == "status" and not rest:
        sys.exit(status())
    if verb == "compare" and len(rest) == 2:
        sys.exit(compare(Path(rest[0]), Path(rest[1])))
    print("Usage: uv run run.py --data status")
    sys.exit(2)
