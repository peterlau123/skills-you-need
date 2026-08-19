---
name: codebase-dependency-audit
description: Use when auditing a Python codebase's third-party deps.
---

# Codebase Dependency Audit

Analyze a large Python codebase (vLLM, transformers, torch ecosystem, forks) to enumerate third-party libraries, find where each is used, and classify required vs optional. Output: structured per-library analysis with concrete file paths and dependency declarations — not a vague summary.

## When to use
- "Research what third-party libraries X uses / what capabilities X has"
- Fork maintenance / porting: which deps must be vendored vs declared
- Due diligence before upgrading, removing, or replacing a dependency
- Answering "is library Y used at runtime, only in tests, or not at all?"

## Workflow

1. **Recon.** List the repo root and the main package dir first. Pin findings to a version: `git log -1`, `version.py`, `pyproject.toml [project]` — dependency sets drift fast.

2. **Find ALL dependency declarations** — not just pyproject.toml:
   - `pyproject.toml`: check `dynamic = ["dependencies"]` — if dynamic, the real list lives elsewhere. Also check `[project.scripts]` / entry-points (plugin registration).
   - `setup.py`: `install_requires=`, `extras_require=` (optional feature extras!), and any `get_requirements()` that picks platform-specific files based on env/auto-detection.
   - `requirements/*.txt`: read EVERY file. Platform files usually `-r common.txt` — full set = common + platform file. Test dirs (`requirements/test/`) are test-only.
   - Build-system deps (cmake, ninja, setuptools-rust) matter when there are C++/Rust extensions.

3. **Import census.** For each candidate library, count Python files referencing it, then dump file lists for the hits. Batch ALL per-library greps into ONE execute_code/terminal script to keep round-trips low:
   `grep -rl --include='*.py' '<pattern>' <pkg_dir> | wc -l` → then `grep -rl ...` for the actual lists.
   If the search_files tool returns 0 for patterns that clearly should match, fall back to grep via terminal — don't trust a single 0.

4. **Per-library deep dive.** For each library with hits:
   - `grep -rn 'from X import\|import X'` for exact import statements + files
   - Read the top 1–3 integration files (the adapter/backend/wrapper that defines the integration)
   - Lazy imports (`importlib.util.find_spec`, try/except ImportError, placeholder modules) → optional at runtime

5. **Check vendored code.** `third_party/`, `vendor/`, or build-time-copied dirs hold third-party code that ships inside the wheel but never appears in requirements (vLLM vendors pynvml, triton_kernels, flashmla, deep_gemm).

6. **Verify negatives.** Absence claims need evidence: grep the import pattern for onnxruntime/openvino/mps/torch_xla/etc., AND grep requirement files to distinguish "test-only" from "runtime" from "absent". Zero-match greps + requirements scan is the proof.

7. **Classify required vs optional:**
   - Listed in runtime requirements file → required
   - Only in `requirements/test/*` → test-only (e.g. bitsandbytes, peft in vLLM are test-only, not runtime)
   - Lazy import / `find_spec` / placeholder module / env-var gated (`VLLM_USE_*`) → optional
   - In `extras_require` → optional feature extra (state the extra name)

8. **Architecture patterns.** Check platform-specific dirs (`platforms/`), allocators (`device_allocator/`), adapter/plugin dirs (`lora/`, `plugins/`, `distributed/device_communicators/`) — this is where per-hardware deps (TPU package, XPU kernels, NCCL/RCCL) and backend-registry patterns surface.

## Pitfalls
- **pyproject with dynamic deps** — reading only pyproject misses the entire dependency list; it lives in setup.py + requirements/.
- **In-tree module name ≠ external package.** `auto_gptq.py` in vLLM is its OWN implementation (imports only torch/safetensors), while `compressed_tensors/` imports the external `compressed-tensors` package. Grep actual `import` statements; never trust filenames.
- **Platform requirement files differ wildly** — Ray may be required on TPU/XPU but optional on CUDA (multiprocessing default). State per-platform.
- **Vendored libs mask real deps** — check `third_party/` before claiming a lib is absent.
- **Namespace collisions** — an import like `from vllm.vllm_flash_attn import ...` is vLLM's own vendored fork of FlashAttention, NOT the `flash-attn` PyPI package. Distinguish fork-of vs upstream-package.

## Verification
- Every library claim cites: dependency declaration file (+line) and 1–3 concrete usage file paths.
- Every "not used" claim backed by a grep that returned nothing or a requirements-only finding.
- Report states the repo version checked.

## Support files
- `references/vllm-third-party-map.md` — worked example: full third-party map of vLLM v0.22.0 (declaration architecture, per-library usage sites, required/optional classification, platform dirs).
