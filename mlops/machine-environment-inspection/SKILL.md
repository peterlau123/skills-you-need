---
name: machine-environment-inspection
description: "Check the host machine: hardware, virtualization, GPUs."
version: 1.0.0
license: MIT
metadata:
  hermes:
    tags: [environment, hardware, gpu, lspci, mx-smi, hostnamectl, inspection]
---

# Machine Environment Inspection

Use when asked "what machine are you on / 机器环境 / 看下环境 / 检查运行环境", before claiming
the host type (cloud vs physical), or when planning resource-dependent work (GPU training/inference).

## Procedure

1. OS & kernel: `uname -a`, `. /etc/os-release && echo $PRETTY_NAME`
2. Hardware identity (physical vs VM/cloud):
   - `hostnamectl` — shows Hardware Vendor + Model (e.g. "New H3C Technologies ... UniServer R5300 G6")
   - `systemd-detect-virt` — `none` = bare metal; `kvm`/`docker`/`wsl` otherwise
   - `ls /.dockerenv` and `grep -i microsoft /proc/version` (container/WSL probes)
3. Scale: `nproc` (threads), `free -h`, `df -h /`, `uptime`, `hostname`
4. GPU / compute accelerators:
   - `lspci | grep -iE "vga|3d|display"` — many display controllers = GPU server
   - Unknown vendor IDs (e.g. `9999:4040`): `lspci -vnn -s <slot>` → read "Kernel driver in use"
     and "Kernel modules" (e.g. `metax`). Confirm identity via the kernel module, not the ID alone.
   - Driver dirs: `ls /usr/local/` for `metax`, `Ascend`, `cambricon`, `iluvatar`, `maca`, `musa`, `corex`
   - Loaded modules: `lsmod | grep -iE "metax|iluvatar|cambricon|ascend|maca"`
   - MetaX cards: `mx-smi` (MetaX's nvidia-smi equivalent, at /usr/bin/mx-smi) → card count, model,
     per-GPU memory/util, kernel driver & MACA versions.
5. Running compute workloads: `ps aux | grep -E "sglang|vllm|python"` — identify inference/training
   services; the `mx-smi` (or nvidia-smi) process section maps PIDs → GPU. The service's own
   command line (`sglang serve --model-path ... --tp N --nnodes M`) reveals model, quantization,
   tensor parallelism, and cluster topology.

## Pitfalls

- NEVER guess the cloud provider from the username — `ecs-user` looked like Alibaba ECS, but the
  box was a physical H3C UniServer R5300 G6. Verify with `hostnamectl` + `systemd-detect-virt`.
- Vendor ID 9999 = MetaX (沐曦), not NVIDIA (10de). On MetaX boxes `nvidia-smi` does not exist —
  `mx-smi` is the tool. Other Chinese GPU vendors to sniff for: Ascend 19e5, Cambricon 1d94,
  Moore Threads 1f90, Iluvatar 1f07 — always confirm with the loaded kernel module.
- `hostname -I` returns the first NIC IP only; multi-node clusters use a different dist-init
  address (e.g. `--dist-init-addr`), so don't equate the box's IP with the cluster endpoint.
- GPU memory can read ~full with 0% util when an inference service (sglang scheduler processes)
  holds weights in VRAM — check the process section before concluding the GPUs are busy.
