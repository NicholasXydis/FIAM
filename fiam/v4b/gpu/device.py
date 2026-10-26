# One place for the torch device and dtype. Float64 everywhere: the ports are
# proved against R/numpy double-precision outputs.

import os

import torch

DTYPE = torch.float64


def device() -> torch.device:
    want = os.environ.get("V4B_DEVICE")
    if want:
        return torch.device(want)
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def tensor(x, dev: torch.device | None = None) -> torch.Tensor:
    return torch.as_tensor(x, dtype=DTYPE, device=dev or device())
