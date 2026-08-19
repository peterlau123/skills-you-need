#!/usr/bin/env bash
# vLLM architecture quick probe — run from the repo root (/data/lx/vllm) after
# checking out the target tag. Prints the key numbers needed for a version
# comparison analysis. Verified against v0.13.0 on 2026-08-14.
set -euo pipefail

REPO="${1:-/data/lx/vllm}"
cd "$REPO"

echo "=== VERSION ==="
git describe --tags 2>/dev/null || echo "(no tags)"

echo "=== FILE COUNT ==="
find vllm/ -name '*.py' -type f | wc -l

echo "=== C++ EXTENSIONS (setup.py) ==="
grep 'CMakeExtension(name=' setup.py | sed 's/.*CMakeExtension(name="\([^"]*\)".*/\1/' || echo "none found"

echo "=== TRITON JIT KERNELS ==="
echo -n "files with @triton.jit: "; grep -rl '@triton.jit' vllm/ --include='*.py' | wc -l
echo -n "total @triton.jit: "; grep -r '@triton.jit' vllm/ --include='*.py' | wc -l

echo "=== TORCH CAPABILITY REF COUNTS (files containing) ==="
for pat in 'torch.distributed' 'torch.compile' 'torch.fx' 'torch.func' 'torch.accelerator' 'torch.library' 'register_fake' 'torch.vmap' 'torch.distributed.nn' 'CUDAPluggableAllocator' 'SymmetricMemory\|symmetric_memory' 'StatelessProcessGroup'; do
  echo -n "  $pat: "
  grep -rl "$pat" vllm/ --include='*.py' 2>/dev/null | wc -l
done

echo "=== KEY DIRECTORIES ==="
for d in vllm/ir vllm/compilation vllm/compilation/passes vllm/platforms vllm/platform vllm/device_allocator vllm/plugins vllm/v1/attention/backends vllm/model_executor/custom_op.py; do
  if [ -e "$d" ]; then echo "  EXISTS: $d"; else echo "  MISSING: $d"; fi
done

echo "=== ATTENTION BACKENDS ==="
ls vllm/v1/attention/backends/*.py 2>/dev/null | xargs -n1 basename | sed 's/\.py$//' | tr '\n' ' '; echo

echo "=== PLUGIN GROUPS ==="
grep -A8 'entry-points' pyproject.toml 2>/dev/null | head -12 || echo "none"

echo "=== TORCH VERSION PIN ==="
grep '^torch==' requirements/cuda.txt 2>/dev/null || grep 'torch==' requirements/cuda.txt 2>/dev/null || echo "(torch not pinned in cuda.txt)"

echo "=== GIT MODIFIED FILES (should be empty if clean) ==="
git status --porcelain | head -5
