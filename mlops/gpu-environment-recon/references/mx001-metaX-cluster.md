# mx001 — user's inference node inventory (verified 2026-08-03)

Node of a 2-node domestic-GPU inference cluster, accessed via Feishu. History: user noted the environment previously ran on Windows; it now runs on this Linux box (no prior session records carried over).

## Hardware (bare metal — systemd-detect-virt = none)
- Physical server: **H3C UniServer R5300 G6** (新华三 4U GPU server), hostname `mx001`, chassis "server"
- CPU: Intel Xeon Platinum 8480+ (224 threads), RAM 2 TB, disk 438G (60% used)
- LAN IP: 10.10.21.33 (private; NOT a cloud VM despite `ecs-user` login name)

## GPU: 8× MetaX C500X (沐曦曦云 C500X)
- 64 GB HBM per card (65536 MiB), 350 W TDP; PCI slots 08/09/0e/11/32/38/3b/3c
- PCI ID `9999:4040` (vendor 0x9999 = MetaX), display controller class
- Kernel driver: METAX 3.9.10 — `/lib/modules/5.15.0-100-generic/extra/metax.ko`, module `metax`
- Compute stack: MACA 3.8.0.23, mx-smi 2.3.4 (`/usr/bin/mx-smi`), `/usr/local/metax/mxdriver`

## Running service (as of 2026-08-03, root, started ~2026-07-22)
- **sglang** serving **MiniMax-M3-W8A8** (`/share/dongg/weights/MiniMax-M3-W8A8`, network share)
- `--tp 16 --nnodes 2 --node-rank 0 --dist-init-addr 10.20.30.23:20000 --mem-fraction-static 0.80 --disable-cuda-graph --disable-overlap-schedule`
- Process tree: `sglang` main + `sglang::scheduler_TP<n>` per GPU (all 8 local cards busy, VRAM ~pre-reserved)
- Runs from `/opt/conda/bin/python3.10` (conda env has sglang; system python3.11 has no torch)

## Hermes
- v0.19.1 (2026.7.30), venv at `/home/ecs-user/.hermes/hermes-agent/venv`, profile `ai-engineer`, binary `/home/ecs-user/.local/bin/hermes`
