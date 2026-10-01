# What this machine's GPU can run: uv run tools/gpu_probe.py. Prints a summary, writes nothing.

import os
import platform
import subprocess
import sys
import time
from pathlib import Path

# The repo root goes on the path, so fiam imports from wherever this is run.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


# PyTorch on the GPU: CUDA on NVIDIA, ROCm on AMD, or the CPU when neither loads.
def torch_route() -> str:
    try:
        import torch
    except ImportError:
        return "PyTorch is not installed here"
    kind = "ROCm" if getattr(torch.version, "hip", None) else "CUDA"
    if torch.backends.mps.is_available():
        return f"PyTorch {torch.__version__} on the Apple GPU (MPS)"
    if not torch.cuda.is_available():
        return f"PyTorch {torch.__version__}: CPU only, no {kind} device"
    device = torch.device("cuda")
    x = torch.randn(4096, 4096, device=device)
    torch.cuda.synchronize()
    started = time.perf_counter()
    for _ in range(10):
        x @ x
    torch.cuda.synchronize()
    speed = 10 * 2 * 4096**3 / (time.perf_counter() - started) / 1e12
    name = torch.cuda.get_device_name(0)
    return f"PyTorch {torch.__version__} on {kind}: {name}, {speed:.1f} TFLOPS in float32"


# llama.cpp's pinned build for this machine, and every device it can see.
def llama_route() -> str:
    from fiam.agents import harness as H

    binary = H.server_binary()
    env = os.environ | {"LD_LIBRARY_PATH": str(binary.parent)}
    listed = subprocess.run(
        [str(binary), "--list-devices"], capture_output=True, text=True, env=env, timeout=120
    )
    devices = [line.strip() for line in listed.stdout.splitlines() if line.strip()]
    return f"llama.cpp build {H.machine()}: " + ("; ".join(devices) or "no GPU device listed")


# Both routes, each reported even when the other fails.
def main() -> None:
    system = f"{platform.system()} {platform.release()}, {platform.machine()}"
    print(f"{system}, Python {platform.python_version()}")
    for name, probe in (("training", torch_route), ("language models", llama_route)):
        try:
            print(f"  {name}: {probe()}")
        except Exception as exc:
            print(f"  {name}: failed, {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()
