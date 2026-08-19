# vLLM v0.13.0 PyTorch Capability Map (diff vs v0.22.0)

Full-tree scan of `/data/lx/vllm/vllm/` at git tag **v0.13.0** (1,131 .py files vs 1,752 in
v0.22.0). Companion to `pytorch-capability-map.md` (which is the v0.22.0 map). Use this when
the question is "what's different in the older v0.13.0 line" or "which capabilities already
existed at v0.13.0". Match counts are grep hits across the package; key paths carry line numbers.

## Delta table (v0.13.0 → v0.22.0)

| Capability | v0.13.0 | v0.22.0 | Verdict |
|---|---|---|---|
| `torch.distributed` | 150 occ / 146 lines / 41 files | 218 | Fewer, more consolidated in `distributed/device_communicators/` |
| `torch.compile` + `_dynamo` | 120 + 57 | 247 combined | Present, same architecture (VllmBackend + Inductor) |
| CUDA graph modes | PIECEWISE/FULL/FULL_AND_PIECEWISE | same + breakable graphs | Mode machinery already existed at v0.13.0 |
| `torch.autograd.Function` | 7 | 7 | Same set (fla, lightning_attn, phimoe) |
| `torch.cuda` (Stream/Event/CUDAGraph) | 70 (52 Stream/Event, 8 CUDAGraph) | 376 | Much thinner; no offloader/multi-stream_utils yet |
| `torch.library` / `torch.ops` | 14 files / 405 ops | 677 | FRAGMENT lib + register_fake already present |
| `torch.fx` | 46 | 57 | Compilation pipeline uses it identically |
| `torch.func` / `vmap` | 1 | 2 | Effectively absent in both |
| `torch.accelerator` | **0** | used (empty_cache/memory_stats) | **v0.13.0 uses only custom `vllm/platforms/`** |
| `torch.utils.cpp_extension` | 1 | 4 | Only pynccl_allocator `load_inline` |
| `torch.distributed.nn` | 0 | 0 | Never used; custom TP layers in both |
| SymmetricMemory | via `torch.distributed._symmetric_memory` import | same | Class name = 0 refs; import path = present |
| StatelessProcessGroup | 18 refs | present | `vllm/distributed/utils.py:144` |

## Per-capability detail (v0.13.0)

1. **torch.distributed — 150 occ / 41 files.** `dist.` alias: 62 refs / 17 files. Imports
   concentrated in `vllm/distributed/device_communicators/*.py` (pynccl.py, custom_all_reduce.py,
   shm_broadcast.py, cuda_communicator.py, cpu_communicator.py), `distributed/communication_op.py`,
   `config/parallel.py`. No `distributed/stateless_coordinator.py` or `weight_transfer/` yet.

2. **torch.compile / _dynamo — `vllm/compilation/` exists (29 files, FLAT — no `passes/` subdir
   like v0.22.0).** `VllmBackend` (backends.py:489) for `CompilationMode.VLLM_COMPILE` (mode=3,
   config/compilation.py:47); `make_compiler` → `InductorAdaptor`/`InductorStandaloneAdaptor`
   (compiler_interface.py:280); `TorchCompileWithNoGuardsWrapper` (wrapper.py:82); `support_torch_compile`
   decorator (decorators.py, 232 refs tree-wide). Passes: `pass_manager.py` (`PostGradPassManager`:62),
   `fusion.py`, `fusion_attn.py`, `activation_quant_fusion.py`, `qk_norm_rope_fusion.py`,
   `collective_fusion.py` (GEMM/ReduceScatter/AllGather/AllReduce+Norm), `sequence_parallelism.py`,
   `fix_functionalization.py`, `noop_elimination.py`, `rocm_aiter_fusion.py`, `caching.py`
   (`torch.fx._graph_pickler.GraphPickler` compile cache), `piecewise_backend.py` (`PiecewiseBackend`),
   `partition_rules.py`, `torch25_custom_graph_pass.py`. `PassConfig` at config/compilation.py:100.

3. **CUDA graphs — `CUDAGraphMode` enum (config/compilation.py:52): NONE/PIECEWISE/FULL/
   FULL_AND_PIECEWISE/FULL_DECODE_ONLY**, helpers `has_mode()/decode_mode()/mixed_mode()`.
   Defaults: V0 = PIECEWISE, V1 = FULL_AND_PIECEWISE (config/vllm.py:131,146,161). Dispatch:
   `vllm/v1/cudagraph_dispatcher.py` (`CudagraphDispatcher`, keys per mode). FULL capture in
   `v1/worker/gpu_model_runner.py` (~30 sites) + `gpu_ubatch_wrapper.py:240` (`torch.cuda.graph(...,
   stream=compute_stream, pool=...)`) + `gpu/cudagraph_utils.py:120`; PIECEWISE via
   `compilation/cuda_graph.py` (`CUDAGraphWrapper`, capture at :266) + piecewise_backend.py.
   `torch.cuda.graph_pool_handle()` at cudagraph_utils.py:53, eagle_cudagraph.py:57,
   platforms/interface.py:602. No `breakable_cudagraph.py`/`encoder_cudagraph.py` (v0.22.0-only).

4. **torch.autograd.Function — 7 refs, none in v1 attention backends.** `lightning_attn.py:396`
   (`_attention`), `fla/ops/chunk.py:74`, `fla/ops/fused_recurrent.py:252`,
   `fla/ops/layernorm_guard.py:250`, `phimoe.py:141` (`mp`); profiler-only refs in
   `v1/utils.py`, `profiler/layerwise_profile.py`.

5. **torch.cuda — 70 refs.** Stream/Event: 52 refs / 18 files (parallel_state.py, ray_communicator.py,
   eplb/*, kv_transfer/*, v1/worker/gpu_model_runner.py, ubatching.py). `CUDAPluggableAllocator`:
   `device_allocator/cumem.py:95` (sleep-mode allocator + `torch.cuda.memory.MemPool`/`use_mem_pool`)
   and `distributed/device_communicators/pynccl_allocator.py:87`. `torch.cuda.set_stream` monkey-patch
   already present (utils/torch_utils.py:363).

6. **torch.library / torch.ops — 405 torch.ops refs** (167 in `vllm/` mostly `_custom_ops.py`,
   97 in `compilation/`, 23 fused_moe, 26 quantization). `vllm_lib = Library("vllm", "FRAGMENT")`
   at utils/torch_utils.py:595; `direct_register_custom_op()` (torch_utils.py:601) with
   `define/impl/_register_fake`. `register_fake`/`impl_abstract`: 39 refs — ~28 `@register_fake("_C::...")`
   in `_custom_ops.py` (gptq/awq/marlin/cutlass/ggml/moe), plus `@torch.library.custom_op` +
   `@register_fake` in `utils/flashinfer.py:380-431`. `Library("aten","IMPL")` mm/addmm override:
   `model_executor/layers/batch_invariant.py:934`.

7. **torch.fx — 46 refs.** `torch.fx.passes.split_module.split_module` (backends.py:331) for
   piecewise splitting, `PiecewiseCompileInterpreter(torch.fx.Interpreter)` (backends.py:358),
   `GraphPickler` (caching.py:62/99), `torch.fx.experimental._config.patch` (decorators.py:507),
   graph rewrites in fix_functionalization.py.

8. **torch.func — 1 ref**: `from torch.func import functional_call` (model_executor/models/utils.py:11,
   used :580). No vmap anywhere.

9. **torch.accelerator — 0 refs.** Device abstraction is vLLM's own `vllm/platforms/` (`Platform` ABC
   interface.py:100, `current_platform`; cuda/rocm/cpu/tpu/xpu.py) with `get_device_capability`,
   `graph_pool_handle()`, `get_compile_backend()`, `get_pass_manager_cls()` (→ default
   `vllm.compilation.pass_manager.PostGradPassManager`, interface.py:191).

10. **torch.utils.cpp_extension — 1 ref**: `load_inline` in pynccl_allocator.py:11 (JIT NCCL allocator).
    Main C++ ops are build-time `CMakeExtension` in setup.py (setup.py imports `CUDA_HOME, ROCM_HOME`
    from torch.utils.cpp_extension; precompiled wheels skip build via `build_extensions` no-op).

11. **torch.distributed.nn — 0 refs.** TP = custom `ColumnParallelLinear` (linear.py:414),
    `RowParallelLinear` (:1242), `QKVParallelLinear` (:867), `MergedColumnParallelLinear` (:586) on
    `distributed/communication_op.py` (`tensor_model_parallel_all_reduce/all_gather/reduce_scatter/gather`).

12. **SymmetricMemory / StatelessProcessGroup — both present.**
    - SymmetricMemory: class name = 0 refs, but `torch.distributed._symmetric_memory` used in
      `compilation/collective_fusion.py:10` (`enable_symm_mem_for_group`, called :406),
      `distributed/device_communicators/symm_mem.py` (`SymmMemCommunicator`), `pynccl_allocator.py`
      (`is_symmetric_memory_enabled`, needs NCCL ≥2.27.3), `parallel_state.py:42`, `all_reduce_utils.py`,
      `envs.py:1451` (VLLM_USE_PYTORCH_SYMMETRIC_MEMORY).
    - StatelessProcessGroup: 18 refs; class at `distributed/utils.py:144` (`create` :367,
      `stateless_init_torch_distributed_process_group` :462); consumers: pynccl.py, shm_broadcast.py,
      eplb_state.py, parallel_state.py.

## Scanning recipe pitfalls learned on this audit

- **Shell word-boundary regexes get eaten**: `grep -rn '\bdist\.' ...` returned 0 falsely (the `\b`
  is mangled through shell quoting). Count alias usage (e.g. `dist.` after `import torch.distributed as dist`)
  with a Python pass instead: `python3 -c "import re,pathlib; ... re.findall(r'\\bdist\\.', txt)"`.
- **f-strings with format specs break inside `python3 -c "..."`** passed through terminal from
  execute_code (NameError on the format variable — shell interprets `{v:5d}`). Use `'%5d %s' % (v,k)`
  formatting in one-liners.
- **"Absent" claims need a broader search first**: SymmetricMemory class name = 0 refs, but the
  `torch.distributed._symmetric_memory` import path is used. Search both the class name AND the
  underlying module path before declaring something absent.
- Count BOTH line refs (`grep -rn ... | wc -l`) and string occurrences (`grep -roh ... | wc -l`) —
  multi-use lines undercount.
