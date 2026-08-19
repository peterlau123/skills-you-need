---
name: vllm-custom-ops
description: "vLLM source: custom ops/kernels, platform dispatch, build."
version: 1.0.0
license: MIT
dependencies: [vllm, torch]
platforms: [linux]
metadata:
  hermes:
    tags: [vLLM, CustomOps, CUDA, Triton, Kernels, torch.ops, PlatformDispatch, SourceInternals]

---

# vLLM Custom Ops & Kernel Integration

## When to use

Use when the task is about the vLLM **source code**, not serving with it:
- Adding or replacing a custom CUDA/C++ kernel, Triton kernel, or torch custom op in vLLM
- Understanding how vLLM dispatches ops per platform (CUDA / ROCm / XPU / CPU / TPU / OOT)
- Figuring out where an op is defined, how it is registered, or why it is not being used
- Porting a kernel between platforms, or plugging in a third-party op/backend/plugin
- Tracing how a kernel call flows from model code down to the `.cu` file

For *using* vLLM as a server (serve CLI, quantization flags, deployment), the bundled
`serving-llms-vllm` skill covers that territory.

## The map in 30 seconds

Everything funnels through `torch.ops`:
- **C++ kernels** → `torch.ops._C::*` (namespace = compiled module name, set by
  `-DTORCH_EXTENSION_NAME` in `cmake/utils.cmake`; registered in `csrc/torch_bindings.cpp` via
  `TORCH_LIBRARY_EXPAND(TORCH_EXTENSION_NAME, ops)` + `ops.def(schema)` + `ops.impl(name, torch::kCUDA, &fn)`).
- **Python-registered fused ops** → `torch.ops.vllm::*` via `direct_register_custom_op()` in
  `vllm/utils/torch_utils.py` (`Library("vllm", "FRAGMENT")` + `define/impl/_register_fake`).
- **IR ops** (newest mechanism, **v0.22.0+ only — `vllm/ir/` does not exist in v0.13.0**) →
  `torch.ops.vllm_ir::*` via `vllm/ir/op.py` `@register_op` +
  `@op.register_impl("provider", supported=..., supports_args=...)`; per-op priority from
  `KernelConfig.ir_op_priority` (`vllm/config/kernel.py`).
- **Triton** → `@triton.jit`, runtime JIT, no registration; big fused blocks (fused MoE) are wrapped
  in a torch custom op so Dynamo sees one opaque node.
- **Platform dispatch is two layers**: `Platform.dispatch_key` + `Platform.import_kernels()`
  (`vllm/platforms/interface.py`, overridden in `platforms/{cuda,rocm,xpu,cpu}.py`) decide which
  extensions load and which dispatch key `torch.library.impl` uses; `CustomOp.dispatch_forward()`
  (`vllm/model_executor/custom_op.py`) picks `forward_native/cuda/hip/xpu/cpu/tpu/oot` per platform.
- **Layout caveat (version-dependent)**: in v0.22.0-era trees, attention code lives in
  `vllm/v1/attention/` — there is no `vllm/attention/` directory. In v0.13.0, `vllm/attention/`
  still exists (`backends/` skeleton + `registry.py`, `layer.py`, `selector.py`, `ops/`,
  `layers/`, `utils/`) but the **concrete backends already live in `vllm/v1/attention/backends/`**
  and the old `vllm/attention/backends/` holds only `abstract.py`, an empty `__init__.py`,
  `registry.py`, `utils.py`. Backends register via `AttentionBackendEnum` + `register_backend()`
  (registry path moved from `vllm/attention/backends/registry.py` → `vllm/v1/attention/backends/registry.py`).

Full detail, code snippets, extension-namespace table, and the discovery grep commands:
**`references/custom-op-kernel-integration.md`** — read it before doing any real work.

For "what PyTorch capabilities does vLLM use" questions (torch.distributed, torch.compile,
CUDA graphs, torch.library, TP layers, AMP, quantization, streams/events, paged KV cache):
**`references/pytorch-capability-map.md`** — capability → file → snippet table with match
counts (v0.22.0-era tree, 1752 .py files), plus the grep-based source-scanning recipe (incl.
the `search_files`/ripgrep-missing fallback to `grep -rEn` via a single batched shell script).
For the same questions against the **older v0.13.0 tree** (1131 .py files), or "what changed
between v0.13.0 and v0.22.0" diffs: **`references/pytorch-capability-map-v013.md`** — delta
table (150 vs 218 torch.distributed, 0 vs used torch.accelerator, no `compilation/passes/`
subdir, etc.) + per-capability paths and extra scanning pitfalls. Always pin the git tag
(`git describe --tags`) before quoting counts — the two maps are version-specific.

For the **operator-integration** side of the same version question (custom-op namespaces,
Triton count, CustomOp framework, plugin groups, `direct_register_custom_op` callers,
attention-backend registry, csrc layout, build system) on the v0.13.0 tree:
**`references/op-integration-v013.md`** — mechanism presence table (IrOp absent, everything
else present), C++ extension inventory (~172 `.def`, 4 TORCH_LIBRARY blocks in
`torch_bindings.cpp`), build-system diff, v0.13.0→v0.22.0 deltas, and the reusable
version-archaeology probe recipe.

For "what third-party libraries does vLLM use" questions (FlashAttention, FlashInfer, Ray,
Transformers, compressed-tensors, FastAPI, etc.):
**`references/third-party-dependency-map.md`** — 13-category dependency map with package
versions, required/optional status, platform availability, and integration points, sourced
from requirements/{common,cuda,rocm,tpu,xpu}.txt + setup.py + pyproject.toml.
For the **older v0.13.0 tree** (torch==2.9.0): **`references/third-party-dependency-map-v013.md`** —
per-library present/absent table vs 0.22.0 plus the delta (QuACK gone, FA4/cutlass-dsl gone,
flashmla + vllm-flash-attn + triton_kernels + qutlass all **source-built via
`cmake/external_projects/*.cmake`, not pip deps**, mooncake connector present but undeclared,
gRPC dropped from serving). Diff the two maps for version-to-version changes.

## Workflow: adding a custom op

1. **Find the integration point**: grep the model/layer for `torch.ops.*` and `_custom_ops as ops`
   to see which namespace the code path uses. Quant GEMMs go through `vllm/_custom_ops.py`
   (`torch.ops._C`), fused blocks through `torch.ops.vllm`, Triton attention is called directly.
2. **C++ route**: add the kernel in `csrc/`, declare schema + impl in the matching `torch_bindings.cpp`,
   add source to `CMakeLists.txt` (`define_extension_target`), add a typed Python facade function in
   `vllm/_custom_ops.py`.
3. **Python route**: write the kernel-calling function, then
   `direct_register_custom_op(op_name=..., op_func=..., mutates_args=[...], fake_impl=...)`.
   Call it as `torch.ops.vllm.<op_name>`.
4. **Always provide a fake/meta impl** (`register_fake` on `_C::op`, or `fake_impl=` on
   `direct_register_custom_op`) — without it torch.compile/graph capture breaks. For in-place ops the
   fake impl is just `pass`.
5. **Respect platform gates**: `Platform.dispatch_key` (ROCm reuses `"CUDA"`!), `import_kernels()`
   overrides (XPU skips `vllm._C` entirely and uses `_xpu_ops.py`; CPU builds `_C_AVX512`/`_C_AVX2`
   variants), and version gates like FA2/FA3 `FAx_AVAILABLE` flags at import time.
6. **Verify**: check the op is registered (`hasattr(torch.ops._C, name)` / `torch.ops.vllm.<op>`),
   run under `torch.compile` to confirm the fake impl fires, and test on the target platform.

## Pitfalls

- **Namespace == module name**: renaming an extension or forgetting `TORCH_EXTENSION_NAME` silently
  changes the `torch.ops` namespace.
- **ROCm dispatches as `"CUDA"`** — HIP kernels register under `torch::kCUDA`; don't add a separate
  ROCm dispatch key.
- **XPU has no `vllm._C`** — `_xpu_ops.py` calls `torch.ops._xpu_C.*` directly and registers a few
  ops into the `vllm` library via `xpu_ops.register_ops_once()`.
- **`mutates_args` matters**: `infer_schema` turns them into `Tensor!` in the schema; wrong
  `mutates_args` breaks autograd/compile correctness for in-place kernels.
- **`Library` object lifetime**: ops registered on a `Library` die with the object — keep the library
  referenced (module-level `vllm_lib`).
- **Don't use `torch.library.custom_op` on hot paths** — vLLM's `direct_register_custom_op` exists
  because it has lower dispatch overhead.
- **`supports_args` vs `supported`** in the IR registry: `supported` is static platform checks only;
  dynamic dtype/shape logic belongs in `supports_args`. Reserved provider names: `native`, `unfused`.
- **Triton tuning configs are cached in JSON** (`model_executor/layers/fused_moe/configs/`) — stale
  tuned configs can override autotune; check them when MoE kernel behavior looks off.
- **Version-gate every source claim**: v0.13.0 (1131 .py files) and v0.22.0 (1752) differ
  materially — no `vllm/ir/` in v0.13.0, `vllm/attention/` still exists there,
  `csrc/custom_all_reduce/` is flat files (subdir later), `_custom_ops.py` 3080 lines/34
  `register_fake` vs ~3900/~40. Run `git describe --tags` and record the commit before quoting
  any count or file path.
- **`search_files` content search can return `[]` inside a git repo** even when matches verifiably
  exist (ripgrep-backed search honors .gitignore/ignore rules). When a search looks suspiciously
  empty, cross-verify with terminal `grep -rlEn`. Bite the `git describe --tags` habit for version-
  specific counts — maps in `references/` are pinned to a version (v0.22.0 vs v0.13.0).

## Key files

| Concern | Path |
|---|---|
| C++ op registry | `csrc/torch_bindings.cpp`, `csrc/core/registration.h`, `csrc/moe/torch_bindings.cpp`, `csrc/rocm/torch_bindings.cpp` |
| Python facade over `_C` | `vllm/_custom_ops.py` (v0.22.0: ~3900 lines, ~40 `register_fake`; v0.13.0: 3080 lines, 34) |
| `torch.ops.vllm` helper | `vllm/utils/torch_utils.py` (`vllm_lib`, `direct_register_custom_op`) |
| Platform dispatch | `vllm/platforms/interface.py` (`dispatch_key`, `import_kernels`), `platforms/{cuda,rocm,xpu,cpu,tpu}.py` |
| Op class framework | `vllm/model_executor/custom_op.py` (`CustomOp`, `PluggableLayer`, `op_registry(_oot)`) |
| IR op registry | `vllm/ir/op.py`, `vllm/ir/ops/layernorm.py`, `vllm/kernels/vllm_c.py`, `vllm/kernels/oink_ops.py` |
| Attention backends | `vllm/v1/attention/backends/registry.py` + `backends/*.py`, `vllm/v1/attention/ops/*` |
| Build system | `setup.py` (`CMakeExtension` list), `CMakeLists.txt`, `cmake/utils.cmake` |
| Plugin entry points | `vllm/plugins/__init__.py` (`vllm.general_plugins`, `vllm.platform_plugins`) |
| XPU ops | `vllm/_xpu_ops.py`; ROCm aiter: `vllm/_aiter_ops.py`; FA2/FA3: `vllm/vllm_flash_attn/flash_attn_interface.py` |
