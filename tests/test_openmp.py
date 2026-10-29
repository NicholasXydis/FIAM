# The OpenMP preload picks the kit's copy only if the system lacks one.

from fiam import openmp


# A machine with the runtime installed needs no preload.
def test_system_runtime_means_no_preload(monkeypatch, tmp_path):
    monkeypatch.setattr(openmp, "machine", lambda: "linux-x64")
    monkeypatch.setattr(openmp, "system_has", lambda name: True)
    assert openmp.preload(tmp_path) == "system"


# Without the system runtime the kit's copy loads, or is reported gone.
def test_kit_copy_loads_when_the_system_lacks_one(monkeypatch, tmp_path):
    loaded = []
    monkeypatch.setattr(openmp, "machine", lambda: "linux-x64")
    monkeypatch.setattr(openmp, "system_has", lambda name: False)
    assert openmp.preload(tmp_path) == "missing"
    (tmp_path / "linux-x64").mkdir()
    (tmp_path / "linux-x64" / "libgomp.so.1").write_bytes(b"x")
    monkeypatch.setattr(openmp.ctypes, "CDLL", lambda path, mode: loaded.append(path))
    assert openmp.preload(tmp_path) == "kit" and loaded[0].endswith("libgomp.so.1")


# Windows wheels carry their own runtime.
def test_windows_needs_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(openmp, "machine", lambda: "windows-x64")
    assert openmp.preload(tmp_path) == "not needed"
