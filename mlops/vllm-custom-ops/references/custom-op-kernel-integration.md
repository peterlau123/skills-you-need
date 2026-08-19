# vLLM Custom Operator & Kernel Integration (source-level map)

Reference map produced by reading a vLLM source checkout (May 2025-era, `/data/lx/vllm`).
Layout caveat: in this version the attention code lives under `vllm/v1/attention/`
(no `vllm/attention/` directory), and a newer IR-op registry lives in `vllm/ir/`.
Use this map when asked to add/extend a kernel, understand op dispatch, port an op to
another platform, or debug why a custom op is (not) being used.

## The integration mechanisms (summary)

| Form | Registration | Where in repo | Used for |
|---|---|---|---|
| C++/CUDA extension | `TORCH_LIBRARY_EXPAND(TORCH_EXTENSION_NAME, ...)` in `.cpp` | `csrc/torch_bindings.cpp`, `csrc/moe/torch_bindings.cpp`, `csrc/rocm/torch_bindings.cpp`; Python facade in `vllm/_custom_ops.py` | paged attention, quant GEMMs (AWQ/GPTQ/Marlin/Machete/CUTLASS-FP8/FP4/INT8), cache ops, custom allreduce, MoE align/topk, oneDNN CPU GEMMs |
| Triton kernels | `@triton.jit`, runtime JIT, no registration | `vllm/v1/attention/ops/triton_*.py`, `vllm/model_executor/layers/fused_moe/*`, `lora/ops/triton_ops/*`, `fla/ops/*` | attention (decode/prefill/unified), default fused MoE, FLA, LoRA |
| Python custom ops into `torch.ops.vllm` | `direct_register_custom_op()` via `Library("vllm", "FRAGMENT")` | `vllm/utils/torch_utils.py` (helper), `fused_moe/fused_moe.py`, `vllm/_xpu_ops.py`, `vllm/compilation/passes/fusion/*` | opaque fused kernels needing fake impls (fused MoE, collective+GEMM fusions, XPU ops) |
| Fake/meta impls | `torch.library.register_fake("_C::opname")` (fallback `impl_abstract`) | ~40 sites in `vllm/_custom_ops.py` | torch.compile tracing of C++ ops |
| IR op registry | `Library("vllm_ir", "FRAGMENT")`, `@register_op` + `@op.register_impl("provider", ...)` | `vllm/ir/op.py`, `vllm/ir/ops/layernorm.py`, `vllm/kernels/vllm_c.py`, `vllm/kernels/oink_ops.py` | ops with swappable impl providers + per-op priority (`KernelConfig.ir_op_priority`) |
| External vendor libs | plain imports, availability-gated | `vllm/_aiter_ops.py` (ROCm aiter), `vllm/vllm_flash_attn/flash_attn_interface.py` (FA2/FA3), flashinfer/deep_gemm backends | FA2 (`torch.ops._vllm_fa2_C.varlen_fwd`), FA3 (`_vllm_fa3_C.fwd`), aiter MoE/attention on ROCm |
| Pure PyTorch | `forward_native()` methods | `model_executor/custom_op.py` framework + every layer | reference impls, CPU/TPU fallbacks, torch.compile-friendly path |

## How the C++ namespace is built

- `setup.py` (~L1035-1094) declares `CMakeExtension(name="vllm._C")` (+ `_C_AVX512`/`_C_AVX2` for x86 CPU,
  `_moe_C`, `_rocm_C`, `_flashmla_C`, `_deep_gemm_C`, `vllm.vllm_flash_attn._vllm_fa2_C`, `_vllm_fa3_C`,
  `cumem_allocator`, `spinloop`), gated on platform (`_is_cuda()`, `_is_hip()`, `_is_cpu()`) and CUDA version.
- `cmake/utils.cmake` (~L599) passes `-DTORCH_EXTENSION_NAME=${MOD_NAME}`; the compiled module name
  **becomes the torch.ops namespace**.
- `csrc/torch_bindings.cpp`: `TORCH_LIBRARY_EXPAND(TORCH_EXTENSION_NAME, ops)` then per-op
  `ops.def("<schema with Tensor! for in-place args>")` + `ops.impl("<name>", torch::kCUDA, &fn)`
  (`kCPU` for CPU-only ops). `csrc/core/registration.h` defines `TORCH_LIBRARY_EXPAND` /
  `CONCAT(TORCH_EXTENSION_NAME, _cache_ops)` → secondary namespaces `_C_cache_ops`, `_C_cuda_utils`,
  `_C_custom_ar`.
- `csrc/moe/torch_bindings.cpp` → `torch.ops._moe_C`; `csrc/rocm/torch_bindings.cpp` → `torch.ops._rocm_C`.

## torch.ops.vllm (the Python-registered namespace)

`vllm/utils/torch_utils.py`:
```python
vllm_lib = Library("vllm", "FRAGMENT")  # → torch.ops.vllm

def direct_register_custom_op(op_name, op_func, mutates_args=None, fake_impl=None,
                              target_lib=None, dispatch_key=None, tags=()):
    schema_str = infer_schema(op_func, mutates_args=mutates_args)
    my_lib = target_lib or vllm_lib
    my_lib.define(op_name + schema_str, tags=tags)
    my_lib.impl(op_name, op_func, dispatch_key=dispatch_key or current_platform.dispatch_key)
    if fake_impl is not None:
        my_lib._register_fake(op_name, fake_impl)
```
Chosen over `torch.library.custom_op` for lower dispatch overhead (see youkaichao's gist link in the
docstring). Default dispatch key = `current_platform.dispatch_key`. Lifetime of the op is tied to the
Library object.

## Platform dispatch (two layers)

Layer 1 — `vllm/platforms/interface.py` `Platform` class:
- `dispatch_key: str = "CPU"`; overrides: CUDA=`"CUDA"`, ROCm=`"CUDA"` (reuses the CUDA registry!),
  XPU=`"XPU"`, CPU=`"CPU"`.
- `import_kernels()` (base): imports `vllm._C` + `vllm._moe_C`.
  - CPU (`platforms/cpu.py:407`): imports `_C_AVX512`/`_C_AVX2`/`_C` depending on
    `torch.cpu._is_avx512_supported()` (module name stays `_C`).
  - ROCm (`platforms/rocm.py:438`): super() + import `vllm._rocm_C`.
  - XPU (`platforms/xpu.py:44`): deliberately skips `_C`, imports only `_moe_C` (XPU has its own
    `_xpu_C` extension + `_xpu_ops.py`).
  - TPU: no C extension.
- `get_attn_backend_cls()`/`get_valid_backends()` per platform selects attention backends.

Layer 2 — `vllm/model_executor/custom_op.py` `CustomOp(nn.Module)`:
- `@CustomOp.register("rms_norm")` etc.; `dispatch_forward()` picks
  `forward_native/cuda/hip/xpu/cpu/tpu/oot` based on `current_platform`, honoring
  `CompilationConfig.custom_ops` (`+op`/`-op`/`all`/`none`) and `enforce_enable`.
- Out-of-tree override: `@CustomOp.register_oot(name=...)` → `op_registry_oot`; `__new__` substitutes
  the class.
- Canonical example: `model_executor/layers/activation.py` `SiluAndMul` — CUDA path grabs
  `torch.ops._C.silu_and_mul` in `__init__` (also used by XPU), `forward_native` is pure torch.

## Module-swap pattern per platform

`vllm/v1/attention/ops/paged_attn.py`:
```python
if current_platform.is_cuda_alike():
    from vllm import _custom_ops as ops
elif current_platform.is_xpu():
    from vllm._xpu_ops import xpu_ops as ops
```
Both modules expose the same function names (`reshape_and_cache`, ...) — a duck-typed ops facade.
`_xpu_ops.py` mixes raw `torch.ops._xpu_C.*` calls with `xpu_ops.register_ops_once()` registering
7 ops into the `vllm` library (`xpu_ops_deepseek_scaling_rope`, `xpu_mxfp8_quantize`, `xpu_mxfp4_quantize`,
`xpu_fp8_mqa_logits`, `xpu_fp8_paged_mqa_logits`, `gdn_attention_core_xpu`, `xpu_topk_topp_sampler`).

## Triton usage pattern (fused MoE)

`vllm/model_executor/layers/fused_moe/fused_moe.py`:
- `@triton.jit` kernels (`fused_moe_kernel`, `fused_moe_kernel_gptq_awq`), autotuned block configs from
  `get_moe_configs()` + model-specific tuned configs in `model_executor/layers/fused_moe/configs/`.
- `dispatch_fused_moe_kernel()` chooses CUDA C++ vs Triton (per quant method / `should_moe_wna16_use_cuda`).
- Exposed as an opaque torch op:
```python
direct_register_custom_op(op_name="inplace_fused_experts", op_func=inplace_fused_experts,
                          mutates_args=["hidden_states"], fake_impl=inplace_fused_experts_fake)
# consumed as torch.ops.vllm.inplace_fused_experts(**kwargs)
```
Fake impl for in-place op is a `pass`. This keeps Dynamo from tracing inside the fused block.

## Attention backends

- `vllm/v1/attention/backends/registry.py`: `AttentionBackendEnum` (values = class paths),
  `register_backend(enum, class_path)` decorator writes into `_ATTN_OVERRIDES`; `enum.get_class()`
  resolves. `CUSTOM = None` placeholder for third-party backends.
- Backends call: `vllm/_custom_ops.py` wrappers → `torch.ops._C.paged_attention_v1/v2`; FA via
  `vllm_flash_attn/flash_attn_interface.py` (`FA2_AVAILABLE`/`FA3_AVAILABLE` version gates at import);
  Triton backends call `decode_attention_fwd`/prefill functions directly.

## Custom allreduce (C++ handle pattern)

`vllm/distributed/device_communicators/custom_all_reduce.py`: `ops.init_custom_ar(...)` returns an
opaque `int` handle; later `ops.all_reduce(ptr, inp, out, ...)`. Template for passing C++ state
across the op boundary.

## IR op registry (newest mechanism)

`vllm/ir/op.py`:
- `@register_op` defines op + native impl; creates `torch.ops.vllm_ir::<op>` via
  `lib.define/impl(dispatch_key="CompositeExplicitAutograd")/_register_fake`.
- `@op.register_impl("provider", supported=..., supports_args=..., inplace=...)` adds alternatives
  ("native" and "unfused" are reserved names). `supports_args` = dynamic dtype/shape check;
  `supported` = static platform check only.
- Dispatch via `set_priority([...])` from `KernelConfig.ir_op_priority` (`vllm/config/kernel.py`,
  `IrOpPriorityConfig` fields like `rms_norm`); platform defaults appended in
  `KernelConfig.set_platform_defaults()`.
- Example: `vllm/kernels/vllm_c.py` registers `vllm_c` provider calling `torch.ops._C.rms_norm`;
  `vllm/kernels/oink_ops.py` shows an external plugin (OINK for SM100) registering under the
  `oink::` namespace.

## How users plug in their own ops (5 official routes)

1. **Custom attention**: subclass backend + `@register_backend(AttentionBackendEnum.CUSTOM)` →
   `--attention-backend custom`.
2. **Custom op/layer**: `@CustomOp.register_oot(name=...)` / `PluggableLayer.register_oot`
   (see `vllm/model_executor/custom_op.py`).
3. **Entry-point plugins**: `vllm.general_plugins` / `vllm.platform_plugins` setuptools groups,
   loaded in every worker by `vllm/plugins/__init__.py` (`load_plugins_by_group`, filter with
   `VLLM_PLUGINS` env var).
4. **Own C++ extension**: build a module with `TORCH_LIBRARY(...)`, call `torch.ops.<ns>.<op>`
   directly, or wrap in a `_custom_ops.py`-style facade + `register_fake`;
   `direct_register_custom_op` is the recommended low-overhead way to expose Python-wrapped kernels
   as `torch.ops.vllm` ops.
5. **IR provider**: `@ir.ops.<op>.register_impl("my_provider", ...)` + set `ir_op_priority.<op>`.

## Discovery commands (how this map was built)

```bash
grep -n "^def \|^class \|torch.ops\._C\.\|register_fake\|register_kernel\|custom_op" vllm/_custom_ops.py | head -200
grep -rn "TORCH_LIBRARY" csrc/*/torch_bindings.cpp
grep -n "CMakeExtension\|ext_modules.append" setup.py
grep -rn "torch.ops.vllm" vllm/ --include="*.py"
grep -rn "torch.library\|direct_register_custom_op" vllm/ --include="*.py"
grep -rln "@triton.jit" vllm/
grep -n "dispatch_key\|import_kernels" vllm/platforms/*.py
```
