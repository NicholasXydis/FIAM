#!/usr/bin/env bash
# One-time agent setup on a Linux NVIDIA machine such as a Lightning AI Studio; run from the repo root.
set -euo pipefail
cd "$(dirname "$0")/../.."

python -m pip install -r requirements.txt huggingface_hub

# The same llama.cpp commit the recorded runs used, built for CUDA instead of Vulkan.
if [ ! -x models/llama.cpp-src/build/bin/llama-server ]; then
  git clone https://github.com/ggml-org/llama.cpp models/llama.cpp-src
  git -C models/llama.cpp-src checkout b11132
  cmake -S models/llama.cpp-src -B models/llama.cpp-src/build -DGGML_CUDA=ON
  cmake --build models/llama.cpp-src/build -j --target llama-server
fi

# The two pinned model files; verify below refuses anything whose hash differs from the manifest.
hf download unsloth/Qwen3.8-27B-GGUF Qwen3.8-27B-UD-IQ4_XS.gguf --local-dir models
hf download unsloth/gemma-4-26B-A4B-it-GGUF gemma-4-26B-A4B-it-UD-IQ4_XS.gguf --local-dir models
python src/agents/harness.py verify

# Hermes at the commit the recorded runs used.
if ! command -v hermes > /dev/null; then
  git clone https://github.com/NousResearch/hermes-agent ~/hermes-agent
  git -C ~/hermes-agent checkout 16fe260a
  (cd ~/hermes-agent && ./setup-hermes.sh)
  export PATH="$HOME/.local/bin:$PATH"
fi
python src/agents/harness.py register

echo "Ready. Copy the organizer's data into data/, then: python run.py --official --agents"
