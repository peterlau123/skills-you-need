---
name: gpu-environment-recon
description: Identify GPU/accelerator hardware, vendor, driver, SMI tool.
---

# GPU Environment Reconnaissance

Trigger: user asks "what's the machine environment / GPUs?", "check the environment", or you need to know which accelerator stack (NVIDIA vs domestic Chinese GPU) is present before installing or running AI tooling.

## Steps

1. **Never guess cloud vs bare metal from the username.** `ecs-user`, `ubuntu`, etc. do NOT indicate a cloud provider. Run:
   - `hostnamectl` — Hardware Vendor/Model line (e.g. "H3C UniServer R5300 G6") and chassis type
   - `systemd-detect-virt` — `none` = bare metal; also check `/.dockerenv` and `/proc/version` (WSL)
2. **List accelerators:** `lspci | grep -iE "vga|3d|display|nvidia"`
3. **Identify vendor** via PCI vendor:device ID (`lspci -vnn -s <slot>`), then confirm with `lsmod`:
   - NVIDIA = `10de` (nvidia module, nvidia-smi)
   - AMD = `1002`; Intel = `8086`
   - **MetaX / 沐曦 = `9999:4040`** — module `metax`, tool `mx-smi`, stack under `/usr/local/metax/`
   - Ascend / 昇腾 = `19e5` — `npu-smi`, `/usr/local/Ascend/`
   - Cambricon / 寒武纪 = `1d94` — `cnmon`/`mlu-smi`
   - Moore Threads / 摩尔线程 = `1f90` — `mthreads-gmi`, `/usr/local/musa/`
   - Iluvatar / 天数智芯 = `1f07` — `ix-smi`
   - Unknown IDs: `lsmod | grep -i <vendor>`, `modinfo <mod>`, and `ls /usr/local/` usually settle it
4. **Driver & compute stack versions:** `modinfo <mod> | grep -E "^(version|filename)"` (MetaX .ko lives at `/lib/modules/<kern>/extra/metax.ko`); the vendor SMI tool header shows stack versions (mx-smi prints "MACA Version").
5. **Monitor cards** with the vendor tool: `nvidia-smi` / `mx-smi` / `npu-smi` ... gives per-GPU temp, power, memory, and a Process table.
6. **Check running workloads:** `mx-smi | sed -n '/Process/,$p'` plus `ps aux | grep -E "sglang|vllm"` — record model path, TP size, node count (sglang CLI args show `--tp`, `--nnodes`, `--dist-init-addr`).

## Pitfalls
- `ecs-user` username does NOT imply Alibaba Cloud ECS — this exact mislabel happened (a physical H3C server was called "cloud ECS" from the username alone). Always verify with `hostnamectl`.
- Absence of `nvidia-smi` does NOT mean "no GPU" — domestic accelerators use their own SMI tools and PCI IDs.
- mx-smi can show ~full memory with 0% util: inference servers (sglang `--mem-fraction-static 0.80`) pre-reserve VRAM at startup.
- GPU serving processes often run as root from `/opt/conda/bin/python3.10` — check `/opt/conda` for torch/sglang, not just system python.

## Support files
- `references/mx001-metaX-cluster.md` — verified inventory of the user's inference node mx001 (H3C R5300 G6, 8× MetaX C500X, sglang serving MiniMax-M3)
