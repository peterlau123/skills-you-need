# vLLM v0.13.0 Operator Integration Map (vs v0.22.0)

Session-verified inventory of the operator-integration mechanisms in the **v0.13.0** tree
(commit `72506c98349d6bcd32b4e33eec7b5513453c1502`, **1131 .py files** vs 1752 in v0.22.0).
Companion to `custom-op-kernel-integration.md` (v0.22.0-era) and
`pytorch-capability-map-v013.md` (capability angle, same tree). All counts below are
grep-verified on the v0.13.0 checkout.

## Mechanism presence table

| Mechanism | v0.13.0 | Key paths / numbers |
|---|---|---|
| C++/CUDA ext via `torch.ops._C::*` | ✅ | `vllm/_custom_ops.py` **3080 lines, 127 `def` fns, 125 `torch.ops._C` refs, 34 `@register_fake`** (torch.library, `impl_abstract` fallback). Line 15: `current_platform.import_kernels()` at import. |
| CustomOp framework | ✅ (same as v0.22.0) | `vllm/model_executor/custom_op.py` (199 lines): `forward_native/cuda/hip/xpu/cpu/tpu/oot` (fallbacks hip→cuda, cpu→cuda, xpu/tpu/oot→native); `op_registry` + `op_registry_oot`; **38 `@CustomOp.register`**; enabled/disabled via `CompilationConfig.custom_ops` (`'all'/'none'/±name`) at `vllm/config/compilation.py:397`. |
| IrOp system (`vllm/ir/`) | ❌ **absent entirely** | No `vllm/ir/` dir, zero `IrOp` refs. Major v0.22.0-only feature (added after v0.13.0). |
| Plugin system (entry_points) | ✅ | `pyproject.toml:44` `[project.entry-points."vllm.general_plugins"]` → `lora_filesystem_resolver`. `vllm/plugins/__init__.py`: 4 groups (`general_plugins`, `io_processor_plugins`, `platform_plugins`, `stat_logger_plugins`), `VLLM_PLUGINS` env filter, `load_general_plugins()` from `engine/arg_utils.py`, `model_executor/models/registry.py:1176`, `v1/engine/core.py:87`, `v1/worker/worker_base.py:250`. |
| `direct_register_custom_op` | ✅ | `vllm/utils/torch_utils.py:595-598` (`vllm_lib = Library("vllm", "FRAGMENT")`, `supports_custom_op()` = `hasattr(torch.library, "custom_op")`). Callers: `compilation/collective_fusion.py:583`, `pynccl.py:51`, `parallel_state.py:250-271` (4 ops), `lora/ops/triton_ops/*` (lora_expand 301, lora_shrink 278, fused_moe_lora 637-651), `flashinfer_trtllm_moe.py:95,186`. **90 `torch.ops.vllm` refs**. Standard try/except pattern: register → `torch.ops.vllm.<name>` → fallback fn on AttributeError. |
| Attention backend registration | ✅ | `vllm/attention/backends/registry.py`: `AttentionBackendEnum` **~23 named + `CUSTOM` placeholder** (FLASH_ATTN, TRITON_ATTN, ROCM_ATTN, ROCM_AITER_*, FLASHINFER(+MLA), TRITON_MLA, CUTLASS_MLA, FLASHMLA(+_SPARSE), FLASH_ATTN_MLA, PALLAS, IPEX, NO_ATTENTION, FLEX_ATTENTION, TREE_ATTN, ROCM_AITER_UNIFIED_ATTN, CPU_ATTN); `register_backend()` overrides. Old-style `vllm/attention/backends/` = only `abstract.py`, **empty `__init__.py`**, `registry.py`, `utils.py` — concrete backends all in **`vllm/v1/attention/backends/`** (18 files + 12 in `mla/`). Selection: `current_platform.get_attn_backend_cls(...)` in `attention/selector.py:96`. |
| Platform-specific dispatch | ✅ | `vllm/platforms/{interface,cuda,rocm,cpu,tpu,xpu}.py`. `interface.py:216 import_kernels()` default imports `vllm._C` + `vllm._moe_C`; `cuda.py` also imports `vllm._C` at top (line 16). Lazy `current_platform` via `resolve_current_platform_cls_qualname()` in `platforms/__init__.py:191` (builtin platform plugins: cuda/rocm/tpu/xpu/cpu fn pointers; OOT plugin support). |
| Triton JIT | ✅ | **133 `@triton.jit` in 60 files**. `vllm/triton_utils/` package (`importing.py`): `HAS_TRITON` + placeholder objects, exports `tl, triton, tldevice`. `torch.library.wrap_triton` in `quantization/qutlass_utils.py:130`. Env-var delegation in `_custom_ops.py` (e.g. `VLLM_USE_TRITON_AWQ` → `awq_triton`, else `torch.ops._C.awq_*`). Hot spots: `lora/ops/triton_ops/`, `model_executor/layers/fla/ops/` (vendored), `fused_moe/`, `mamba/ops/`, `v1/attention/backends/`. |

## C++ extension modules & registration

- Main `csrc/torch_bindings.cpp` (**836 lines, 4 `TORCH_LIBRARY_EXPAND` blocks**):
  `ops` (98 defs), `_cache_ops` (12), `_cuda_utils` (2), `_custom_ar` (16, incl. ROCm quick-reduce under `#ifdef USE_ROCM`). Ends with `REGISTER_EXTENSION(TORCH_EXTENSION_NAME)`.
- Separate bindings: `csrc/moe/torch_bindings.cpp` (13 defs), `csrc/cpu/torch_bindings.cpp` (3 libs: main + `_utils` + `_cpu`), `csrc/rocm/torch_bindings.cpp`.
- ~17 `TORCH_LIBRARY_IMPL_EXPAND` blocks inline in kernel `.cu` files (marlin family, machete, gptq_marlin, awq_marlin, cutlass_w4a8, nvfp4, hadamard, moe ops, sm100_cutlass_mla). **~172 total `.def` across csrc .cpp**.
- `csrc/core/registration.h`: `TORCH_LIBRARY_EXPAND` / `TORCH_LIBRARY_IMPL_EXPAND` (macro-name-expanding variants) + `REGISTER_EXTENSION(NAME)` which emits `PyInit_<name>` so the .so initializes on Python import.
- **`csrc/custom_all_reduce/` is NOT a subdirectory in v0.13.0** — flat `csrc/custom_all_reduce.cu/.cuh` + `csrc/custom_quickreduce.cu` at csrc root (became a subdir in later versions).

## Build system (v0.13.0)

- `setup.py` `CMakeExtension` list: `vllm._C`, `vllm._moe_C`, `vllm.cumem_allocator`, `vllm.triton_kernels` (optional), `vllm._rocm_C` (ROCm), `vllm.vllm_flash_attn._vllm_fa2_C` / `_vllm_fa3_C`, `vllm._flashmla_C` + `_flashmla_extension_C` (optional). SABI 3 → `*.abi3.so`.
- `CMakeLists.txt`: min 3.26, C++17, `VLLM_TARGET_DEVICE` cache var (cuda/hip/cpu), Python 3.10–3.13, torch 2.9.0; `define_extension_target()` helper at `cmake/utils.cmake:485` (`Python_add_library MODULE`, `USE_SABI`, `WITH_SOABI`, hipify pre-step). Marlin/moe-marlin kernels auto-generated from `generate_kernels.py` scripts.
- External FetchContent: **cutlass v4.2.1**, **vllm-flash-attn @ GIT_TAG 86f8f157cf82aa2342743752b97788922dd7de43** (built into `vllm/vllm_flash_attn/`, which is **empty in git — only a `.gitkeep`**; the Python `flash_attn_interface` comes from the fetched repo), flashmla, qutlass, triton_kernels (`cmake/external_projects/*.cmake`).

## v0.13.0 → v0.22.0 deltas (op integration)

1. **`vllm/ir/` IrOp system added** — the single biggest difference; v0.13.0 predates it entirely.
2. `_custom_ops.py` grew **3080 → ~3900 lines**; `register_fake` 34 → ~40.
3. Layout: in v0.13.0 **`vllm/attention/` exists** (`backends/` skeleton + `registry.py`, `layer.py`, `selector.py`, `ops/`, `layers/`, `utils/`); by v0.22.0-era the directory is gone and everything lives under `vllm/v1/attention/`.
4. `csrc/custom_all_reduce/` → became a subdirectory later; flat files in v0.13.0.
5. `current_platform.import_kernels()` invoked from `_custom_ops.py` module top (line 15) in v0.13.0.
6. Python file count 1131 vs 1752 (~35% growth).

## Reusable probe recipe (any vLLM version)

1. **Pin the tag first**: `git describe --tags` + `git log -1 --format='%H %s'`; record both in output. All counts are version-specific.
2. Existence probes: `ls`/`wc -l` on `vllm/_custom_ops.py`, `vllm/ir/`, `vllm/model_executor/custom_op.py`; `grep -n 'entry-points' pyproject.toml`; `find vllm -type d -name ir`.
3. Count inventory (cheap, high signal): `grep -c 'torch.ops._C'` / `'^def '` / `'@register_fake'` in `_custom_ops.py`; `grep -r '@triton.jit' | wc -l` and files-with count; `grep -c 'ops.def'` per `torch_bindings.cpp`; `grep -rn '@CustomOp.register' | wc -l`; `grep -rn 'torch.ops.vllm' | wc -l`.
4. Read registration blocks: head/tail of `csrc/torch_bindings.cpp`, `csrc/core/registration.h`, `custom_op.py` `dispatch_forward`, `platforms/interface.py` `import_kernels`, `plugins/__init__.py`.
5. Build diff: `setup.py` `ext_modules` list vs `CMakeLists.txt` `define_extension_target` calls vs `cmake/external_projects/*.cmake`; note SABI/optional extensions.
6. Watch version-specific layout traps: attention backend location (`vllm/attention/` vs `vllm/v1/attention/`), csrc subdir vs flat files, empty placeholder dirs (`.gitkeep`).
