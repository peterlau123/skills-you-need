---
name: vllm-source-analysis
description: "Use when analyzing vLLM source or comparing vLLM versions."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [vllm, source-analysis, operator-integration, architecture, version-comparison]
---

# vLLM Source Architecture Analysis

Use when the user asks to analyze the vLLM codebase (`/data/lx/vllm`), understand how operators
integrate, compare versions (e.g. v0.13.0 vs v0.22.0), or assess third-party dependencies. The
user is a vLLM + MetaX GPU adaptation engineer — these analyses feed technical reports, papers,
and adaptation work (see memory). Reply in Chinese.

## Repo facts (mx001)

- Repo: `/data/lx/vllm`. Tags available locally: `v0.13.0`, `v0.13.0rc1-4`, plus a sync branch —
  **no v0.2x tags are fetched locally**, so a git-diff across major versions is impossible;
  compare by checking out the tag and re-counting.
- Check out: `git stash && git checkout v0.13.0`, verify with `git describe --tags`.
- Scale: v0.13.0 = 1131 Python files / ~429k lines; v0.22.0 = ~1752 files (+55%).

## The core question: how do C++ extensions integrate?

Not all vLLM extensions go through `torch.ops._C::*`. Three invocation classes (verified v0.13.0,
still the model for later versions):

1. **torch.ops-registered namespaces** — `vllm._C` → `torch.ops._C::*` (~125 refs in
   `vllm/_custom_ops.py`); `vllm._moe_C` → its OWN namespace `torch.ops._moe_C::*` (independent
   `TORCH_LIBRARY` block in `csrc/moe/torch_bindings.cpp`, 13 ops). Don't lump _moe_C under _C.
2. **Python import + direct function call** — `vllm.vllm_flash_attn._vllm_fa2/fa3_C` (call
   `flash_attn_varlen_func` directly), `vllm._flashmla_C` (`import vllm._flashmla_C` then
   `flash_mla_with_kvcache`), `vllm._rocm_C`. The `.so` loads via `REGISTER_EXTENSION` →
   `PyInit_<name>` (csrc/core/registration.h), NOT the ops registry.
3. **Non-ops interfaces** — `vllm.cumem_allocator` implements PyTorch `CUDAPluggableAllocator`
   (registered as a memory allocator, `torch.cuda.memory.CUDAPluggableAllocator`), and
   `vllm.triton_kernels` is a C++ wrapper of Triton kernels imported as a plain module.

Build-time extension list: `grep 'CMakeExtension(name=' setup.py` (9 modules in v0.13.0:
`_C`, `_moe_C`, `cumem_allocator`, `triton_kernels`, `_rocm_C`, `_vllm_fa2_C`, `_vllm_fa3_C`,
`_flashmla_C`, `_flashmla_extension_C`). External kernels come via CMake FetchContent
(cutlass v4.2.1, vllm-flash-attn, FlashMLA, triton_kernels, qutlass) — NOT vendored in git
(e.g. `vllm/vllm_flash_attn/` is a `.gitkeep` placeholder).

## Analysis workflow

1. `git checkout <tag>` + `git describe --tags` to confirm.
2. Count scale: `find vllm/ -name '*.py' | wc -l`.
3. Run the quick probes (see `scripts/vllm_arch_probe.sh`) for: extension list from setup.py,
   `@triton.jit` count (133 in 60 files at v0.13.0), `torch.distributed` / `torch.compile` /
   `torch.fx` / `torch.func` / `torch.accelerator` ref counts, presence of key dirs
   (`vllm/ir/`, `vllm/compilation/passes/`, `vllm/platforms/`).
4. For feature absence claims, VERIFY with targeted grep before asserting — a first-pass grep
   this session wrongly claimed the plugin system was absent in v0.13.0 when it existed
   (`vllm/plugins/` with 4 entry-point groups, `pyproject.toml:44`). Absence is a strong claim.
5. For big comparisons, dispatch parallel subagents (one per theme: operator integration /
   PyTorch capabilities / third-party deps) — they produce much deeper counts than quick greps.
6. Deliver results into a Feishu doc (see `feishu-docs` skill): **primary analyzed version as
   main body, newer version's deltas as an appendix** (user preference, 2026-08-14).

## Version landmarks (v0.13.0 vs v0.22.0)

- v0.13.0 is **V1-only** (`vllm/engine/llm_engine.py` is a one-line shim to v1).
- v0.13.0 has NO `vllm/ir/` (IrOp system is post-0.13), no QuACK, no Rust frontend, no
  `_C_AVX512/_C_AVX2`, no spinloop, torch==2.9.0 (v0.22.0: 2.11.0 + torch.accelerator).
- v0.13.0 compilation passes are flat in `vllm/compilation/`; v0.22.0 reorganizes into
  `passes/fusion/` and adds BreakableCUDAGraphCapture.
- Both versions share: CustomOp framework (8 dispatch targets, 38 `@CustomOp.register`),
  `direct_register_custom_op` + `Library("vllm", "FRAGMENT")`, plugin system, ~23 attention
  backends (v0.13.0), SymmetricMemory, StatelessProcessGroup, ctypes NCCL wrapper.

## Pitfalls

- `search_files` (ripgrep) returned EMPTY for files that verifiably contain the pattern —
  likely .gitignore filtering in the repo. Fall back to `grep -r` in terminal; it's authoritative.
- `grep 'CMakeExtension(name='` in a python3 -c heredoc inside a bash string breaks on the
  parentheses — use a file or `grep` directly, not nested python -c with quotes.
- No pip in Hermes venv python3.11 — use `/usr/bin/python3` (3.10) for any package installs.
