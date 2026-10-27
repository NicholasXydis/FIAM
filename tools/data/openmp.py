# OpenMP runtimes for LightGBM on fresh machines, receipted.

import hashlib
import io
import json
import platform
import subprocess
import sys
import tarfile
import time
import urllib.request

from _shared import ROOT, stamp

OUT = ROOT / "models" / "openmp"
USAGE = "uv run run.py --data openmp fetch | verify"
DEBIAN = "https://deb.debian.org/debian/pool/main/g/gcc-12"
GHCR = "https://ghcr.io/v2/homebrew/core/libomp/blobs/sha256:"
# Each machine's archive, its SHA-256 and the library inside it.
SOURCES = {
    "linux-x64": (
        f"{DEBIAN}/libgomp1_12.2.0-14+deb12u1_amd64.deb",
        "48fec46bda7f5b1638b9e959889bfbc20491247d402d120bb152687eb48143d7",
        "libgomp.so.1",
    ),
    "linux-arm64": (
        f"{DEBIAN}/libgomp1_12.2.0-14+deb12u1_arm64.deb",
        "a48b70dd1a95585466b40bd94564bce56ebcb2566e49ccdb6441e996aaab2098",
        "libgomp.so.1",
    ),
    "mac-arm64": (
        GHCR + "77809f8d10514453e246625d9433141d5f666083e2dd52d82a2631250b89551c",
        "77809f8d10514453e246625d9433141d5f666083e2dd52d82a2631250b89551c",
        "libomp.dylib",
    ),
    "mac-x64": (
        GHCR + "569a93ca1ac3c3674c56055baddd0f9697a95a32cc2f3c485da3d7c8a53711f4",
        "569a93ca1ac3c3674c56055baddd0f9697a95a32cc2f3c485da3d7c8a53711f4",
        "libomp.dylib",
    ),
}


# One download, with GHCR's anonymous token header, retried when busy.
def get(url: str) -> bytes:
    last = None
    for wait in (0, 10, 30):
        time.sleep(wait)
        try:
            headers = {"User-Agent": "FIAM research", "Authorization": "Bearer QQ=="}
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except OSError as err:
            last = err
    raise last


# The members of a Debian package, an ar archive of named blobs.
def ar_members(blob: bytes) -> dict[str, bytes]:
    if not blob.startswith(b"!<arch>\n"):
        raise ValueError("not a Debian package")
    members, at = {}, 8
    while at < len(blob):
        name = blob[at : at + 16].decode().strip().rstrip("/")
        size = int(blob[at + 48 : at + 58].decode().strip())
        members[name] = blob[at + 60 : at + 60 + size]
        at += 60 + size + (size % 2)
    return members


# The library file inside an archive, following a symlink to its target.
def extract(blob: bytes, library: str) -> bytes:
    if blob.startswith(b"!<arch>\n"):
        data = next(v for k, v in ar_members(blob).items() if k.startswith("data.tar"))
        archive = tarfile.open(fileobj=io.BytesIO(data), mode="r:*")
    else:
        archive = tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz")
    with archive:
        found = [m for m in archive.getmembers() if m.name.endswith("/" + library)]
        member = found[0]
        if member.issym():
            target = member.linkname.rsplit("/", 1)[-1]
            member = next(m for m in archive.getmembers() if m.name.endswith("/" + target))
        return archive.extractfile(member).read()


# Mac library renamed @rpath/libomp.dylib and signed, so preloads count.
def prepare_mac(path) -> None:
    subprocess.run(["install_name_tool", "-id", "@rpath/libomp.dylib", str(path)], check=True)
    subprocess.run(["codesign", "-f", "-s", "-", str(path)], check=True, capture_output=True)


# Fetches each machine's library into models/openmp with a receipt.
def fetch() -> int:
    book = {}
    for name, (url, sha, library) in SOURCES.items():
        blob = get(url)
        got = hashlib.sha256(blob).hexdigest()
        expected = sha
        if got != expected:
            print(f"{name}: archive hash {got[:12]} is not {expected[:12]}; nothing saved")
            return 1
        folder = OUT / name
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / library
        path.write_bytes(extract(blob, library))
        if name.startswith("mac") and platform.system() == "Darwin":
            prepare_mac(path)
        lib_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        book[name] = {"url": url, "archive_sha256": got, "library": library}
        book[name] |= {"library_sha256": lib_sha, "prepared_at": stamp()}
        print(f"{name}: {library} saved ({path.stat().st_size >> 10} KB)", flush=True)
    (OUT / "receipts.json").write_text(json.dumps(book, indent=1))
    return 0


# Every saved library against its receipt.
def verify() -> int:
    book_path = OUT / "receipts.json"
    if not book_path.exists():
        print("openmp: not fetched yet")
        return 1
    bad = 0
    for name, entry in json.loads(book_path.read_text()).items():
        path = OUT / name / entry["library"]
        ok = (
            path.exists()
            and hashlib.sha256(path.read_bytes()).hexdigest() == entry["library_sha256"]
        )
        bad += not ok
    print(f"openmp: {bad} wrong")
    return 1 if bad else 0


# One verb per run.
if __name__ == "__main__":
    verbs = {"fetch": fetch, "verify": verify}
    verb = sys.argv[1] if len(sys.argv) > 1 else ""
    if verb not in verbs:
        print(f"Usage: {USAGE}")
        sys.exit(2)
    sys.exit(verbs[verb]())
