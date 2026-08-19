# vLLM Third-Party Dependency Map — v0.13.0

Source: `/data/lx/vllm` — vLLM **v0.13.0** (`git describe --tags`), torch==2.9.0,
requires-python `>=3.10,<3.14`. Verified 2026-08-14 by scanning `requirements/*.txt`,
`setup.py` (extras + `get_requirements()`), `pyproject.toml`, `cmake/external_projects/*.cmake`,
`vllm/utils/import_utils.py` (`has_*()`), attention backend registry, and `kv_transfer` connectors.

Companion to `references/third-party-dependency-map.md` (v0.22.0) — diff the two maps for
version-to-version changes. Where this map says "vs 0.22.0" the comparison comes from that file.

## Where deps are declared (v0.13.0) — read ALL of these

| Location | What it holds |
|---|---|
| `requirements/common.txt` | ~54 shared runtime deps (compressed-tensors==0.12.2, fastapi[standard], pyzmq, msgspec, gguf, anthropic, mcp, ...) |
| `requirements/cuda.txt` | numba==0.61.2, ray[cgraph]>=2.48.0, torch==2.9.0, torchaudio, torchvision, **flashinfer-python==0.5.3** |
| `requirements/rocm.txt` | datasets, ray[cgraph], peft, tensorizer, runai-model-streamer, **conch-triton-kernels==1.2.1**, timm, fastsafetensors (git) |
| `requirements/kv_connectors.txt` | lmcache, **nixl >= 0.7.1** (no mooncake!) |
| `requirements/build.txt` | cmake, ninja, packaging, setuptools, setuptools-scm, torch==2.9.0, wheel, jinja2, regex, build |
| `setup.py` extras | bench, tensorizer, fastsafetensors, runai, audio, video, flashinfer (empty, compat), petit-kernel |
| **`cmake/external_projects/*.cmake`** | **Source-built libs that appear NOWHERE in requirements** — always check this dir |
| `vllm/utils/import_utils.py` | `has_*()` = optional runtime modules: has_pplx, has_deep_ep, **has_deep_gemm**, has_triton_kernels, has_tilelang, has_arctic_inference |

Key insight: **the biggest kernel libs (FlashAttention fork, FlashMLA, triton_kernels, qutlass)
are FetchContent'd and compiled at build time — they are NOT pip dependencies.** Auditing
requirements*.txt alone misses them.

## cmake/external_projects (built from source)

| Project | Repo @ tag | Produces |
|---|---|---|
| `vllm_flash_attn.cmake` | `github.com/vllm-project/flash-attention` @ `86f8f157cf82aa2342743752b97788922dd7de43` | `vllm/vllm_flash_attn/_vllm_fa2_C.abi3.so`, `_vllm_fa3_C.abi3.so` + copied .py files (overridable via `VLLM_FLASH_ATTN_SRC_DIR`) |
| `flashmla.cmake` | `github.com/vllm-project/FlashMLA` (vllm fork of deepseek-ai/FlashMLA) @ `46d64a8ebef03fa50b4ae74937276a5c940e3f95` | `vllm/_flashmla_C.abi3.so`, `vllm/_flashmla_extension_C.abi3.so` (sm90a/sm100a only, CUDA>=12.3) |
| `triton_kernels.cmake` | `triton-lang/triton` @ tag `v3.5.0` | `vllm.triton_kernels` extension (optional) |
| `qutlass.cmake` | `IST-DASLab/qutlass` @ `830d2c4537c7396e14a02a46fbddd18b5d107c65` | qutlass quantized kernels (used via `quantization/qutlass_utils.py`) |

`vllm/vllm_flash_attn/` in the source tree is an **empty `.gitkeep` placeholder** (no submodule,
no `.gitmodules`); the real package lands there only after build.

## Per-library status (parent checklist, vs 0.22.0)

| # | Library | v0.13.0 | Notes / delta vs 0.22.0 |
|---|---|---|---|
| 1 | FlashAttention | **PRESENT, source-built** | Fork fetched at build time via CMake (see above); no `vllm-flash-attn` pip dep. Usage: `from vllm.vllm_flash_attn import flash_attn_varlen_func, get_scheduler_metadata` (fa_utils.py, mla/flashattn_mla.py), `layers/rotary`. No FA4 in v0.13.0 (0.22.0 had `_vllm_fa4_cutedsl_C` + cutlass-dsl). |
| 2 | FlashInfer | **PRESENT, heavily used** | `flashinfer-python==0.5.3` (0.22.0: 0.6.11.post2). Backend `v1/attention/backends/flashinfer.py` + `FLASHINFER_MLA`; MoE: flashinfer_cutlass/cutedsl/trtllm_moe; quant: `vllm/utils/flashinfer.py` (fp4, trtllm fp8), flashinfer_fp4_moe.py, NVFP4; comm: `flashinfer.comm` (MNNVL/trtllm all2all) in all2all.py, mnnvl_compat.py. |
| 3 | Triton | **PRESENT, 133 `@triton.jit`** | Not a declared dep — guarded by `HAS_TRITON` in `vllm/triton_utils/` (placeholder classes); arrives via torch. ROCm pins triton==3.5.0. Big users: fla/ops (10 files), fused_moe (6), mamba/ops (7), quantization utils, lora/ops/triton_ops, mrope, batch_invariant, flashmla_sparse. Count differs from 0.22.0 — no 0.22.0 tree available to diff exact numbers. |
| 4 | DeepGEMM | **PRESENT, optional module** | `fused_moe/{deep_gemm_moe,deep_gemm_utils,batched_deep_gemm_moe,triton_deep_gemm_moe}.py` + `vllm/utils/deep_gemm.py`; `has_deep_gemm()`; NOT in requirements (0.22.0 declared `deepgemm` pip package + built `_deep_gemm_C`). |
| 5 | FlashMLA | **PRESENT, source-built** | vllm-project/FlashMLA fork @ build time. Backends: FLASHMLA + FLASHMLA_SPARSE (fp8 sparse); ops in `attention/ops/flashmla.py` (flash_mla_with_kvcache, get_mla_metadata, flash_mla_sparse_prefill). Plus CUTLASS SM100 MLA: `csrc/attention/mla/cutlass_sm100_mla/` + `csrc/cpu/mla_decode.cpp`. 6 MLA backends total: flashmla, flashmla_sparse, triton_mla, cutlass_mla, flashattn_mla, flashinfer_mla (+rocm aiter variants). |
| 6 | QuACK | **ABSENT** | Zero hits (case-insensitive) in vllm/, requirements/, setup.py. 0.22.0 had `quack-kernels>=0.3.3` for the FA4 path. (Don't confuse with `quantization/quark/` = Intel Quark.) |
| 7 | Ray | **PRESENT, core** | `ray[cgraph]>=2.48.0` in cuda.txt AND rocm.txt (0.22.0 map called it optional/TPU-required — now required for PP). `v1/executor/{ray_executor,ray_distributed_executor,ray_utils}.py`, `ray_communicator.py` (ray.experimental.channel), `vllm/ray/`. |
| 8 | NCCL | **PRESENT, direct ctypes** | `pynccl_wrapper.py` = ctypes `NCCLLibrary` (ncclComm_t, ncclUniqueId, ncclRedOpTypeEnum); `pynccl.py` PyNcclCommunicator; `pynccl_allocator.py` (symmetric mem); `vllm/utils/nccl.py` `find_nccl_library()` (VLLM_NCCL_SO_PATH → libnccl.so.2/librccl.so.1); kv_transfer p2p connectors. Not a pip dep. |
| 9 | NIXL | **PRESENT** | `kv_transfer/kv_connector/v1/nixl_connector.py` (lazy `from nixl._api import nixl_agent`); `nixl >= 0.7.1` in kv_connectors.txt (0.22.0: >=1.1.0); `get_nixl_supported_devices()` on platform interface. |
| 10 | Mooncake | **PRESENT as connector, NOT declared** | `mooncake_connector.py` (lazy `from mooncake.engine import TransferEngine`, zmq+msgspec) but **missing from requirements/kv_connectors.txt** (0.22.0 declared `mooncake-transfer-engine>=0.3.8`) — user must install manually. |
| 11 | compressed-tensors | **PRESENT** | `compressed-tensors == 0.12.2` in common.txt (0.22.0: 0.15.0.1). `quantization/compressed_tensors/` schemes: w4a16_24, w4a16_nvfp4, w4a4_nvfp4, w4a8_fp8, w4a8_int, w8a16_fp8, w8a8_fp8 + compressed_tensors_moe.py, triton_scaled_mm.py. |
| 12 | bitsandbytes | **PRESENT as method, not a dep** | `quantization/bitsandbytes.py`; only in test.in/test.txt/nightly_torch_test.txt (==0.46.1). |
| 13 | torchao | **PRESENT as method, not a dep** | `quantization/torchao.py` (TorchAOConfig, torchao_version_at_least); `default_loader.py` `safetensors_load_strategy="torchao"` needs torchao>=0.14/0.15. Not in requirements (0.22.0 also optional). |
| 14 | FastAPI / gRPC | **FastAPI yes, gRPC no** | fastapi[standard]>=0.115.0 in common.txt; entrypoints/openai + anthropic + sagemaker; uvicorn launcher. gRPC absent from serving — only OTel OTLP exporter (tracing.py) + grpcio==1.71.0 in test.txt (0.22.0 had grpcio==1.78.0 as RPC engine service). |
| 15 | Declared deps | see file list above | Not declared anywhere: triton (runtime), deep_gemm, deep_ep, flashmla (source-built), vllm-flash-attn (source-built), bitsandbytes, torchao, mooncake. |

## Structural facts (v0.13.0)

- **V0 engine fully removed**: `vllm/engine/llm_engine.py` is a one-line shim → `vllm.v1.engine.llm_engine`. V1-only architecture.
- **Attention backends live in `vllm/v1/attention/backends/`** (registry-based `AttentionBackendEnum`): flash_attn, flashinfer, triton_attn, flex_attention (torch native), tree_attn, gdn_attn, rocm_aiter_* family, pallas, cpu_attn, mamba backends (mamba1/mamba2/short_conv/linear/gdn under `MambaAttentionBackendEnum`), plus `mla/` subdir (6 MLA backends). `vllm/attention/backends/` contains only abstract/registry/utils scaffolding.
- **`vllm/platforms/` (plural — NOT `platform/`)**: cpu.py, cuda.py, rocm.py, tpu.py, xpu.py, interface.py. cuda.py does flashinfer/FlashMLA backend selection (`is_flashmla_dense_supported`, `use_flashinfer_mla`), fp8 support, pynvml.
- **`vllm/device_allocator/` EXISTS**: cumem.py `CuMemAllocator` (cuMem-based pluggable torch allocator for sleep mode; backed by `csrc/cumem_allocator.cpp`); used from `v1/worker/gpu_worker.py`.
- Other csrc highlights: `custom_quickreduce.cu`, `quickreduce/`, `quantization/`, `moe/`, `mamba/`, `attention/` (paged_attn_v1/v2, merge_attn_states, vertical_slash_index, mla/cutlass_sm100_mla).

## Scanning notes / pitfalls

- **`search_files` content search returned `[]` for matches that verifiably exist** inside this git repo (fastapi, flashinfer, nixl, compressed_tensors all came up empty; terminal `grep -r` found them). Ripgrep-backed search respects .gitignore/ignore rules — cross-verify with `grep -rl` via terminal when a search looks suspiciously empty in a git tree. (Same pitfall already recorded for the pytorch-capability scans.)
- Always `git describe --tags` first — counts and maps are version-specific.
- `flashinfer-python==0.5.3` is pinned in cuda.txt "should be updated together with the Dockerfile" — check the Dockerfile when auditing versions.
