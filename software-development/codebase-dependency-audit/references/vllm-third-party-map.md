# vLLM v0.22.0 — Third-Party Dependency Map (worked example)

Audited `/data/lx/vllm` (synced to upstream v0.22.0; torch 2.11.0; Python 3.10–3.14; Rust frontend `vllm-rs`). Method: see SKILL.md workflow.

## Declaration architecture
- `pyproject.toml`: deps are **dynamic** (`dynamic = ["dependencies"]`); build-system = cmake, ninja, setuptools-rust, torch==2.11.0. Entry points register LoRA resolvers (`vllm.plugins.lora_resolvers.*`).
- `setup.py`: `get_requirements()` selects ONE platform file via `VLLM_TARGET_DEVICE` auto-detect (cuda/rocm/xpu/cpu; macOS forced to cpu). Builds C++ via `CMakeExtension` (extensions: `vllm._C`, `_C_stable_libtorch`, `_moe_C`, `_flashmla_C`, `cumem_allocator`, `spinloop`, `vllm.vllm_flash_attn._vllm_fa{2,3}_C`, `_rocm_C`…) and Rust `vllm-rs` binary via `RustExtension`.
- `extras_require`: zen (zentorch), bench, tensorizer, fastsafetensors, instanttensor, runai, audio (av/scipy/soundfile), video, flashinfer, helion, grpc (smg-grpc-servicer), otel.
- `requirements/common.txt` (~58 universal) + platform files each `-r common.txt`; `requirements/kv_connectors.txt` optional.

## Runtime deps by category (all in common.txt unless noted)
- **Attention/kernels**: `vllm_flash_attn` (vendored FA2/FA3/FA4 fork — NOT `flash-attn` PyPI; C++ in `csrc/`, glue in `vllm/vllm_flash_attn/`, FA3 needs CUDA≥12.3); FlashInfer (cuda.txt: `flashinfer-python==0.6.11.post2` + `flashinfer-cubin`; ~70 usage files incl. `v1/attention/backends/flashinfer.py`, MLA, MoE, all-reduce; `utils/flashinfer.py` wrapper downloads cubins from NVIDIA artifactory); Triton (GPU required, `triton_utils/` handles optionality via `HAS_TRITON`); tilelang + apache-tvm-ffi (cuda.txt); nvidia-cutlass-dsl/quack-kernels/humming-kernels (cuda.txt, FA4/cute-DSL + quant GEMM); tokenspeed-mla (cuda.txt, MLA spec decode). xformers: NOT installed by default — only `model_executor/models/pixtral.py` lazy import.
- **Distributed**: Ray (optional on CUDA/CPU — multiprocessing default; REQUIRED on TPU/XPU per tpu.txt/xpu.txt; `v1/executor/ray_executor*.py`, `ray_utils.py`, `vllm/ray/lazy_utils.py`, placement groups in `v1/engine/core.py`); NCCL via torch.distributed AND direct ctypes in `distributed/device_communicators/pynccl_wrapper.py` (loads libnccl.so.2/librccl.so.1, `utils/nccl.py:find_nccl_library()`, env `VLLM_NCCL_SO_PATH`); pyzmq (IPC engine↔workers, `shm_broadcast.py`); msgspec (fast serialization, `kv_events.py`).
- **HF ecosystem**: transformers (374 files; core `transformers_utils/` — config.py, processors/ with 30+ custom processors, repo_utils.py); tokenizers (v1/engine/detokenizer.py); sentencepiece (indirect via mistral_common); safetensors (weight_utils.py) + fastsafetensors (cuda.txt); tiktoken (grok2/kimi_audio tokenizers); mistral_common[image] (pixtral/voxtral); modelscope (lazy, `VLLM_USE_MODELSCOPE`).
- **Serving**: fastapi[standard], uvicorn (launch.py), aiohttp, openai client (Responses API), anthropic (entrypoints/anthropic/), mcp, smg-grpc (extra grpc), watchfiles, openai-harmony (gpt-oss), model-hosting-container-standards.
- **Structured output**: xgrammar (arch-gated), llguidance, outlines_core==0.2.14 (not `outlines`), lm-format-enforcer==0.11.3, lark, diskcache, partial-json-parser. Backends in `v1/structured_output/`.
- **Quantization**: compressed-tensors==0.15.0.1 (pinned, external package imported by in-tree `quantization/compressed_tensors/`); gguf; torchao/modelopt/fbgemm (lazy, optional); bitsandbytes **test-only** (not in runtime reqs; `quantization/bitsandbytes.py` + `bitsandbytes_loader.py` legacy path); auto-gptq/autoawq NOT used externally — vLLM own impls (`quantization/auto_gptq.py`, `awq.py`, `awq_marlin.py`); amd-quark (rocm.txt); tensorizer/runai-model-streamer/instanttensor (extras).
- **Spec decode**: numba==0.65.0 (N-gram proposer, `v1/spec_decode/ngram_proposer.py`).
- **LoRA**: NO external peft/punica at runtime. In-tree `vllm/lora/`: `punica_wrapper/` (punica_base/cpu/gpu/xpu) uses own Triton kernels (`lora/ops/triton_ops/`); `peft_helper.py` = own PEFT-config parser. (`vllm/adapter/` does NOT exist.)
- **Metrics**: prometheus_client, prometheus-fastapi-instrumentator, opentelemetry (in common.txt AND extra `otel`; `tracing/otel.py` OTLP + tracecontext).
- **Multimodal**: pillow, opencv-python-headless (video IO, `multimodal/video.py`), einops (Qwen2-VL), av/scipy/soundfile (extra audio), timm (rocm.txt).

## GPU/low-level
- pynvml: **VENDORED** at `vllm/third_party/pynvml.py` (copied from nvidia-ml-py 12.570.86 — rationale in `utils/import_utils.py:import_pynvml()`: avoids the conflicting unofficial pynvml package).
- tcmalloc bundled into CPU wheels (`setup.py:bundle_tcmalloc`).
- `vllm-rs` Rust binary: tokenizer/chat-renderer/tool-parser/reasoning-parser frontend (`VLLM_USE_RUST_FRONTEND`).

## Absent (verified by grep, zero matches)
OpenVINO, ONNX Runtime, MPS/Metal (macOS forced CPU-only), torch_xla (TPU stack replaced by `tpu-inference` package).

## Platform / allocator / adapter dirs
- `vllm/platforms/`: interface.py (`Platform` base: PlatformEnum, dist_backend, ray_device_key) + cuda.py (pynvml, `_C`, NCCL availability), rocm.py (RCCL, upstream flash_attn fallback, bnb compat), tpu.py (imports `tpu_inference.platforms.TpuPlatform` — 21-line file), xpu.py (imports `vllm_xpu_kernels._C/_moe_C/_xpu_C`), cpu.py/zen_cpu.py (zentorch extra).
- `vllm/device_allocator/cumem.py`: CUDA VMM allocator ("sleep mode") via `vllm.cumem_allocator` C ext (`csrc/cumem_allocator.cpp`) + `CudaRTLibrary` ctypes; comment: ctypes/cuda-python failed due to CUDA context mismatch → C extension.
- Backend registry pattern: `v1/attention/backends/registry.py` (`AttentionBackendEnum` FLASH_ATTN/FLASHINFER/TRITON_ATTN/CPU/GDN/ROCm/MLA + `register_backend()` for third-party custom backends). Feature flags in `envs.py` (~60 `VLLM_USE_*` vars) gate optional integrations.
