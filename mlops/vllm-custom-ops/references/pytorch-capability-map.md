# vLLM PyTorch Capability Map (source-level)

Condensed from a full-tree scan of `/data/lx/vllm/vllm/` (1752 .py files, requires
`torch==2.11.0` per `requirements/cuda.txt`). Use when asked "what PyTorch features does
vLLM use" or when navigating the source by capability. Match counts are grep hits across
the package.

## Capability → where → what for

| Capability | Matches | Key files | What it's for |
|---|---|---|---|
| `torch.distributed` | 218 | `distributed/parallel_state.py` (57), `distributed/utils.py`, `distributed/stateless_coordinator.py`, `distributed/weight_transfer/{ipc_engine,nccl_engine}.py`, `distributed/elastic_ep/elastic_state.py`, `config/parallel.py` | `GroupCoordinator` (parallel_state.py:290) wraps ALL collectives. NOT `torch.distributed.nn` (0 hits — vLLM writes its own TP layers). Uses `init_process_group`, `new_group`, `send/recv`, `broadcast_object_list`, `all_gather_object`, `isend/irecv` (eplb), `_functional_collectives` (funcol), `_symmetric_memory`, and a `StatelessProcessGroup` that replaces `init_process_group` via `ProcessGroup`/`TCPStore`/`rendezvous` |
| `torch.compile` / `_dynamo` | 247 | `compilation/wrapper.py` (18), `compilation/decorators.py`, `model_executor/layers/activation.py`, `config/compilation.py`, `v1/attention/backends/flex_attention.py`, `compilation/backends.py`, `model_executor/layers/fused_moe/utils.py`, `vocab_parallel_embedding.py` | `CompilationMode` (STOCK vs custom). Model compiled via `self.model.compile(fullgraph=True, backend=...)` (gpu_model_runner.py:5171) or `torch.compile(..., options=...)` in wrapper.py:148. Dynamo config tuned (`cache_size_limit=2048`), guards dropped via `torch.compiler.skip_all_guards_unsafe`, per-kernel `@torch.compile(dynamic=True, backend=current_platform.simple_compile_backend)` |
| CUDA graphs | 439 | `v1/worker/gpu_model_runner.py` (50), `config/compilation.py`, `v1/cudagraph_dispatcher.py`, `compilation/breakable_cudagraph.py`, `compilation/cuda_graph.py`, `v1/worker/gpu/cudagraph_utils.py`, `v1/worker/encoder_cudagraph.py` | Capture-per-batch-size, replay on steady state. `torch.cuda.CUDAGraph()` + `with torch.cuda.graph(cudagraph, pool=..., stream=...)` (cuda_graph.py:283/313). `CudagraphDispatcher` picks graph per batch descriptor; `BreakableCUDAGraphWrapper` does runtime stream-capture (alternative to FX splitting). Capture-aware collectives check `torch.cuda.is_current_stream_capturing()` |
| `torch.library` / `torch.ops` | 677 | `_custom_ops.py` (191), `compilation/passes/fusion/collective_fusion.py`, `_aiter_ops.py` (ROCm), `_xpu_ops.py` (XPU), `utils/flashinfer.py`, `model_executor/layers/batch_invariant.py`, `csrc/torch_bindings.cpp` | Every custom kernel is `torch.ops._C.*` (paged_attention_v1/v2, rms_norm, rotary_embedding, awq/gptq gemm, cutlass_scaled_mm, custom_ar...). Newer ops: `torch.library.custom_op` + `@register_fake` (flashinfer.py:505). **`torch.library.Library("aten","IMPL")` overrides `aten::mm/addmm/matmul/linear` per-SM for determinism** (batch_invariant.py:913). C++ side: `TORCH_LIBRARY_EXPAND(TORCH_EXTENSION_NAME, ops)` in csrc/torch_bindings.cpp:18 |
| `torch.autograd` | 7 | `model_executor/layers/fla/ops/fused_recurrent.py` (:481 `FusedRecurrentFunction`), `model_executor/layers/fla/ops/chunk.py`, `model_executor/layers/lightning_attn.py` (:397 `_attention`), `profiler/layerwise_profile.py` | Only special attention impls (FLA recurrent/chunk, lightning attn) need custom forward/backward. Inference itself runs under `torch.inference_mode()`/`no_grad` (97 hits) |
| `torch.cuda` | 376 | `v1/worker/gpu_model_runner.py` (28), `platforms/{cuda,rocm}.py`, `model_executor/offloader/prefetch.py`, `utils/torch_utils.py`, `distributed/eplb/eplb_communicator.py`, `v1/worker/gpu/async_utils.py`, `utils/multi_stream_utils.py`, `v1/worker/gpu_worker.py` | Multi-stream (compute/copy/aux) for KV offload, weight prefetch, async D2H; `Event` sync; memory accounting (`mem_get_info`, `empty_cache`, `memory_stats`, `reset_peak_memory_stats`, `max_memory_allocated`). **Monkey-patches `torch.cuda.set_stream` to track streams** (torch_utils.py:669-712) |
| `torch.profiler` | 12 | `profiler/wrapper.py` (8), `v1/engine/async_llm.py`, `profiler/layerwise_profile.py` | `ProfilerActivity.{CPU,CUDA,XPU}`, `torch.profiler.profile(schedule=..., on_trace_ready=tensorboard_trace_handler)`, `record_function` |
| `torch.jit` | 18 | `model_executor/models/phi4mm_utils.py` (8), `siglip2navit.py`, `qwen3_omni_moe_thinker.py`, `interns1_vit.py` | Only to interop with upstream vision-model TorchScript annotations (`torch.jit.Final`, `torch.jit.is_scripting()`). vLLM never scripts its own modules |
| `torch.fx` | 57 | `compilation/passes/utility/fix_functionalization.py` (13), `compilation/backends.py`, `compilation/codegen.py`, `compilation/passes/vllm_inductor_pass.py`, `compilation/caching.py`, `compilation/passes/fusion/sequence_parallelism.py` | Custom compile pipeline splits the model graph for per-piece CUDA-graph capture: `torch.fx.Graph`/`Node`/`GraphModule` rewrites, codegen re-emits Python from `split_gm`, `torch.fx._lazy_graph_module` |
| `torch.utils.cpp_extension` | 4 | `distributed/kv_transfer/kv_connector/v1/hf3fs/hf3fs_client.py` (3), `distributed/device_communicators/pynccl_allocator.py` | Runtime JIT: `load_inline` compiles an NCCL-backed CUDA allocator (`ncclMemAlloc`/`ncclMemFree`) — see below |
| AMP | 12 | `model_executor/models/nemotron.py` (6), `transformers_utils/processors/cohere_asr.py`, `model_executor/models/mimo_audio.py`, `fla/ops/chunk.py` | `torch.amp.autocast("cuda")`, `torch.amp.autocast_mode._cast`, `torch.is_autocast_enabled` — only in encoder/ASR-style models; main path uses native fp16/bf16 weights |
| Quantization | 201 | `model_executor/layers/quantization/` (whole tree), `models/deepseek_v4/common/ops/cache_utils.py`, `_custom_ops.py`, `fused_moe/utils.py` | **Custom quant framework, `torch.quantization` itself = 0 hits.** Uses torch dtypes (`torch.float8_e4m3fn`, `float8_e5m2`, `uint8`) + torchao (`layers/quantization/torchao.py`, `torch.library.wrap_triton` in qutlass_utils.py) |
| TP layers | custom | `model_executor/layers/linear.py` (ColumnParallelLinear :410, RowParallelLinear :1392, QKVParallelLinear :975, MergedColumnParallelLinear :607), `vocab_parallel_embedding.py` (:192), `logits_processor.py`, `fused_moe/layer.py`, `distributed/communication_op.py`, `v1/attention/backends/mla_attention.py` | `tensor_model_parallel_all_reduce/gather/reduce_scatter` wrappers over `get_tp_group()` — NOT `torch.distributed.nn` |
| Custom allreduce | 563 all_reduce / 326 all_gather | `distributed/device_communicators/cuda_communicator.py` (40 — dispatcher), `quick_all_reduce.py` (ROCm), `custom_all_reduce.py` (29), `flashinfer_all_reduce.py` (20), `pynccl.py` (ctypes NCCL), `all2all.py`, `eplb/` (isend/irecv), `cpu_communicator.py` (Gloo+SHM) | Backend dispatch order: NCCL symm-mem → quick_reduce → flashinfer → custom_allreduce → pynccl. `pynccl.py` calls `ncclAllReduce` via ctypes on a `torch.cuda.Stream` (`stream.cuda_stream`) |
| Paged KV cache | — | `v1/core/kv_cache_manager.py`, `v1/worker/gpu/attn_utils.py`, `v1/worker/gpu_model_runner.py` (:6863-6997), `v1/attention/ops/paged_attn.py`, `v1/attention/backends/flash_attn.py`, `_custom_ops.py` (:114-206) | KV cache = big `torch.Tensor` shape `(2, num_blocks, block_size, num_kv_heads, head_size)` (flash_attn.py:149), allocated `torch.zeros(..., dtype=torch.int8)` + reshaped via `torch.as_strided`; `PagedAttention.split_kv_cache` views into key/value caches; kernels write via block tables + `slot_mapping` |
| `torch.vmap`/func | 2 | `model_executor/offloader/uva.py` (:9), `model_executor/models/gemma4.py` (:330) | `torch.func.functional_call` for parameter substitution (UVA offloader), not vmap |
| `torch._C` | 19 | `profiler/layerwise_profile.py` (`_C._profiler`, `_C._autograd`), `distributed/utils.py` (:630 `_register_process_group`), `env_override.py` (monkey-patches `torch._inductor` internals) | Profiler internals, named-group registration for dynamo, inductor patching |

## Notable engineering patterns (reuse when reading/porting vLLM code)

1. **Collectives as custom ops for dynamo**: `GroupCoordinator.all_reduce` dispatches to
   `torch.ops.vllm.all_reduce(input_, group_name=self.unique_name)` — group passed as a
   *string* because Dynamo can't pass arbitrary objects to custom ops. Fake impls
   (`all_reduce_fake` → `torch.empty_like`) let tracing succeed (parallel_state.py:130-170, 514-534).
2. **Group name registry**: `_register_process_group`/`_unregister_process_group` from
   `torch._C._distributed_c10d` register named groups so collectives can be looked up by name
   inside compiled code (distributed/utils.py:630).
3. **NCCL-backed CUDA pluggable allocator**: `pynccl_allocator.py` uses
   `torch.cuda.memory.CUDAPluggableAllocator` + `torch.utils.cpp_extension.load_inline` with
   `ncclMemAlloc`/`ncclMemFree` so CUDA-graph pools can share symmetric memory across ranks.
4. **`torch.library.Library("aten", "IMPL")` per-device overrides** for determinism
   (batch_invariant.py) — SM80 gets triton mm/addmm overrides; SM90+ only cuBLAS workspace config.
5. **Stream bookkeeping**: `torch.cuda.set_stream` is monkey-patched to track the current
   stream (torch_utils.py) — vLLM forked streams heavily (offloader prefetch, KV offload,
   deepseek_v4 multi-stream attention with `[torch.cuda.Event() for _ in range(4)]`).
6. **`torch.accelerator.*`** (new generic device API) used alongside `torch.cuda`:
   `torch.accelerator.empty_cache()`, `memory_stats()`, `device_index()` — abstraction over
   cuda/xpu (gpu_worker.py, pynccl.py).
7. **Not present**: `torch.export` (0), `torch.quantization` (0), `torch.distributed.nn` (0),
   `torch.utils.benchmark` (0).

## How this map was produced (scanning recipe)

`search_files`/ripgrep may be unavailable on the host (`rg: command not found`); plain `grep`
always works. Inside `execute_code`, each `terminal()` call counts against the 50-call cap —
**write ONE bash script with a `scan() { label, pat }` function that emits
`===== label =====\n<count>\n--- top files ---\n<file:count sorted desc>` to a file, run it
once, then read the file.** Use `grep -rEn "$pat" $BASE --include='*.py'` for counts and
`grep -rlE ... | while read f; do echo "$f:$(grep -cE "$pat" "$f")"; done | sort -t: -k2 -nr`
for per-file heatmaps. Then extract snippets with `grep -nE`/`sed -n` on the top files.
Regex gotchas: escape parens in patterns like `torch\.distributed\.([a-z_]+)`, and prefer
`grep -E` with `\.` escapes over plain `grep` to avoid brace/paren interpretation.
