# vLLM Third-Party Dependency Map

Source: `/data/lx/vllm` — vLLM v0.22.0 (torch==2.11.0, Python 3.10–3.14).
Verified 2026-08-14 by scanning `requirements/common.txt`, `requirements/cuda.txt`,
`requirements/rocm.txt`, `requirements/tpu.txt`, `requirements/xpu.txt`, `requirements/test/cuda.txt`,
`pyproject.toml`, and `setup.py`.

## Dependency declaration architecture

| File | Role |
|---|---|
| `pyproject.toml` | Build system (cmake, ninja, setuptools-rust, torch==2.11.0); deps are dynamic (`[project] dependencies` references `setup.py:get_requirements()`) |
| `setup.py:get_requirements()` | Platform-specific dep loading: `common.txt` + `{cuda,rocm,tpu,cpu,xpu}.txt` |
| `requirements/common.txt` | ~60 shared deps (transformers, tokenizers, fastapi, prometheus, opentelemetry, etc.) |
| `requirements/cuda.txt` | CUDA-only deps (flashinfer, cutlass-dsl, deepgemm, humming-kernels, etc.) |
| `requirements/rocm.txt` | ROCm deps (amd-quark, conch-triton-kernels, tilelang) |
| `requirements/tpu.txt` | TPU deps (tpu-inference, torch_xla, ray[data]) |
| `requirements/xpu.txt` | Intel XPU deps (vllm_xpu_kernels, auto_round_lib) |

## 1. Attention / CUDA kernel libraries

| Library | Package | Required? | Purpose | Integration point |
|---|---|---|---|---|
| FlashAttention FA2 | `vllm.vllm_flash_attn._vllm_fa2_C` (built-in fork) | Required (CUDA) | High-efficiency attention, reduced HBM access | `vllm/vllm_flash_attn/flash_attn_interface.py` |
| FlashAttention FA3 | `vllm.vllm_flash_attn._vllm_fa3_C` | Optional (CUDA 12.9+) | FA3 kernels | Same module, gated by `FA3_AVAILABLE` |
| FlashAttention FA4 | `vllm.vllm_flash_attn._vllm_fa4_cutedsl_C` | Optional (cutlass-dsl) | FA4 cute-DSL implementation | Same module |
| FlashInfer | `flashinfer-python==0.6.11.post2` | Optional (CUDA) | High-perf attention + sampler, fused allreduce | `vllm/v1/attention/backends/flashinfer.py` |
| FlashMLA | `vllm._flashmla_C` | Optional (CUDA 12.9+) | Multi-head Latent Attention (DeepSeek) | `vllm/v1/attention/backends/mla/` |
| DeepGEMM | `vllm._deep_gemm_C` | Optional (SM90/SM100) | High-perf matrix multiplication | MoE GEMM path |
| QuACK | `quack-kernels>=0.3.3` | Optional (CUDA) | FA4 cute-DSL kernels | FA4 path |
| Triton | `triton==3.6.0` (via torch) | Required | JIT GPU kernel compilation | `vllm/kernels/triton/`, `vllm/model_executor/layers/fused_moe/` |
| nvidia-cutlass-dsl | `nvidia-cutlass-dsl[cu13]==4.5.2` | Optional | CUTLASS DSL | FA4 build |
| tilelang | `tilelang==0.1.9` | Optional | TileLang kernels | CUDA/ROCm |
| conch-triton-kernels | `conch-triton-kernels==1.2.1` | Optional (ROCm) | ROCm Triton kernels | ROCm attention |
| tokenspeed-mla | `tokenspeed-mla==0.1.2` | Optional (CUDA) | MLA + speculative decode acceleration | MLA path |
| humming-kernels | `humming-kernels[cu13]==0.1.2` | Optional (CUDA) | Mixed precision quantization GEMM | Quantization |
| vllm_xpu_kernels | external whl | Optional (XPU) | Intel XPU-specific kernels | `vllm/_xpu_ops.py` dispatch |

## 2. Model loading & tokenization

| Library | Version | Purpose |
|---|---|---|
| transformers | >=4.56.0 | Model config (AutoConfig), tokenizers, image/video processors. vLLM does NOT use HF model.forward — only config + processor. |
| tokenizers | >=0.21.1 | Fast incremental detokenization |
| sentencepiece | (common) | LLaMA tokenizer |
| tiktoken | >=0.6.0 | DBRX/Grok tokenizer (`vllm/tokenizers/grok2.py`, `vllm/tokenizers/kimi_audio.py`) |
| mistral_common | >=1.11.2 | Mistral tokenizer + image processor |
| safetensors | >=0.6.2 | Safe model weight loading (MXFP4/MXFP6 dtype support) |
| fastsafetensors | >=0.2.2 | Parallel safetensors loading |
| gguf | >=0.17.0 | GGUF format model loading |
| cloudpickle | (common) | Lambda function serialization (model registry) |
| openai-harmony | >=0.0.3 | gpt-oss compatibility |

## 3. Distributed & communication

| Library | Required? | Purpose | Notes |
|---|---|---|---|
| Ray | Optional (TPU required) | Distributed inference engine, multi-node/multi-GPU scheduling | Supports Ray Compiled DAG (`VLLM_USE_RAY_COMPILED_DAG_*` env vars) |
| NCCL | Via torch (nvidia-nccl-cu13==2.28.9) | GPU collective communication | vLLM also implements CustomAllReduce (P2P bypass NCCL) |
| NIXL | Optional (kv_connectors) | Disaggregated prefill communication | `nixl>=1.1.0` |
| Mooncake | Optional (kv_connectors) | High-performance transfer engine | `mooncake-transfer-engine>=0.3.8` |
| lmcache | Optional (kv_connectors) | KV cache caching | `lmcache>=0.3.9` |
| gRPC (grpcio) | Optional | RPC engine service | `grpcio==1.78.0` |
| pyzmq | >=25.0.0 | ZeroMQ message queue | ZMQ-based worker communication |
| cupy-cuda12x | Optional (ROCm/test) | CUDA Python bindings | `cupy-cuda13x` on CUDA 13 |

## 4. Quantization

| Library | Platform | Purpose |
|---|---|---|
| compressed-tensors | All | Unified quantization model format loading (==0.15.0.1) |
| bitsandbytes | CUDA (test) | int8/fp8 quantization |
| auto_round_lib | XPU | AutoRound quantization |
| amd-quark | ROCm | Quark quantization on ROCm |
| torchao | Optional | torchao prototype quantization (`vllm/model_executor/layers/quantization/torchao.py`) |
| modelopt | CUDA | NVIDIA ModelOpt quantization |

## 5. Serving framework

| Library | Purpose |
|---|---|
| FastAPI (>=0.115.0) | OpenAI-compatible API server |
| uvicorn | ASGI server |
| aiohttp (>=3.13.3) | Async HTTP |
| msgspec | High-performance serialization |
| openai (>=2.0.0) | Responses API + reasoning content compatibility |
| anthropic (>=0.71.0) | Anthropic API compatibility |
| mcp | Model Context Protocol |

## 6. Observability

| Library | Purpose |
|---|---|
| prometheus_client (>=0.18.0) | Prometheus metrics |
| prometheus-fastapi-instrumentator (>=7.0.0) | FastAPI auto-instrumentation |
| opentelemetry-sdk/api/exporter-otlp (>=1.27.0) | OpenTelemetry distributed tracing |
| opentelemetry-semantic-conventions-ai (>=0.4.1) | AI semantic conventions |
| python-json-logger | Structured JSON logging |
| depyf (==0.20.0) | torch.compile debugging/profiling |
| setproctitle | Process name setting for debugging |
| psutil | System resource monitoring |

## 7. Multimodal

| Library | Purpose |
|---|---|
| Pillow (PIL) | Image processing |
| opencv-python-headless (>=4.13.0) | Video processing |
| torchvision (==0.26.0) | phi3v image processor |
| torchaudio (==2.11.0) | Audio processing |
| einops | Qwen2-VL tensor rearrangement |
| av (PyAV) | Video decoding |
| decord | Video frame extraction |

## 8. Structured output

| Library | Version | Purpose |
|---|---|---|
| xgrammar | >=0.2.0 | Grammar-guided generation (x86_64/aarch64) |
| outlines_core | ==0.2.14 | Outlines structured output |
| llguidance | >=1.7.0 | LLM guidance |
| lm-format-enforcer | ==0.11.3 | Format constraint |
| lark | ==1.2.2 | Grammar parsing |
| partial-json-parser | (common) | Partial JSON parsing |
| diskcache | ==5.6.3 | Outlines backend disk cache |

## 9. Speculative decoding

| Library | Purpose |
|---|---|
| numba (==0.65.0) | N-gram speculative decoding |
| arctic-inference | Arctic inference optimization |
| EAGLE (built-in) | Eagle speculative decoder (`vllm/v1/worker/gpu/spec_decode/eagle/`) |
| rejection_sampler (built-in) | Rejection sampling (`vllm/v1/worker/gpu/spec_decode/`) |

## 10. LoRA

| Library | Purpose |
|---|---|
| peft | LoRA weight loading (test dep) |
| Built-in LoRA | `vllm/v1/worker/lora_model_runner_mixin.py`, `vllm/model_executor/layers/lora/` |
| LoRA resolvers | `vllm/plugins/lora_resolvers/filesystem_resolver.py`, `hf_hub_resolver.py` |

## 11. Platform-specific

### NVIDIA CUDA
- torch==2.11.0+cu130 (CUDA 13.0)
- nvidia-cudnn-frontend (>=1.13.0,<1.19.0), nvidia-cutlass-dsl, nvidia-nvshmem-cu13==3.4.5

### AMD ROCm
- vllm._rocm_C (ROCm-specific C++ extension)
- amd-quark, conch-triton-kernels, tilelang

### Intel XPU
- torch==2.11.0+xpu
- vllm_xpu_kernels (external wheel), auto_round_lib

### Google TPU
- tpu-inference==0.19.0, torch_xla
- ray[default], ray[data] (required on TPU)

### CPU
- vllm._C_AVX512 / vllm._C_AVX2 (AVX instruction set optimized variants)
- py-cpuinfo (CPU info detection)

## 12. Memory management

| Component | Purpose |
|---|---|
| vllm.cumem_allocator | CUDA driver API-based custom memory allocator (sleep mode support) |
| PyTorch CUDA caching allocator | Standard torch memory management |
| torch.cuda.memory_pool | Memory pool management |

## 13. Other notable deps

| Library | Purpose |
|---|---|
| setuptools-rust (>=1.9.0) | Rust extension compilation (vllm-rs frontend) |
| regex | High-performance regex (replaces re) |
| blake3 | Fast hashing |
| filelock (>=3.16.1) | File locking |
| cbor2 | Cross-language serialization |
| ijson | Mistral streaming tool parser |
| watchfiles | TLS file monitoring for HTTP server |
| pybase64 | Fast base64 implementation |
| model-hosting-container-standards | Container standards compliance |
