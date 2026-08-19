# skills-you-need

A comprehensive collection of AI agent skills for Hermes Agent (by Nous Research).

## Overview

This repository contains 104 skills across 16 categories, designed for the Hermes Agent ecosystem. Each skill lives in its own folder with a `SKILL.md` that follows the standard skill format (YAML frontmatter + markdown body).

## Categories

| Category | Count | Description |
|----------|-------|-------------|
| `apple/` | 4 | Apple ecosystem: Notes, Reminders, FindMy, iMessage |
| `autonomous-ai-agents/` | 7 | Multi-agent orchestration: Claude Code, Codex, OpenCode, etc. |
| `creative/` | 15 | Content generation: ASCII art, diagrams, infographics, music, etc. |
| `email/` | 1 | Terminal email via Himalaya CLI |
| `github/` | 7 | GitHub workflow: auth, issues, PRs, code review, repo management |
| `mattpocock/` | 15 | Matt Pocock's engineering skills: TDD, debugging, code review, etc. |
| `media/` | 4 | Media processing: YouTube, Bilibili, GIF search, audio analysis |
| `mlops/` | 8 | ML ops: GPU recon, HuggingFace, vLLM serving, evaluation, etc. |
| `note-taking/` | 2 | Obsidian vault integration + AI infra wiki |
| `ponytail/` | 1 | Lazy-but-effective solution finder |
| `productivity/` | 13 | Documents: PDF, DOCX, XLSX, PPTX, Feishu, Notion, Google Workspace, etc. |
| `provenance-tracing/` | 1 | Trace claims/IPs to their origin |
| `research/` | 6 | Academic research: arXiv, blog monitoring, LLM wiki, Polymarket |
| `smart-home/` | 1 | Philips Hue control via OpenHue CLI |
| `social-media/` | 1 | X/Twitter via xurl CLI |
| `software-development/` | 13 | Dev workflow: debugging, TDD, code review, planning, simplification |
| `web/` | 1 | Jekyll/Chirpy blog editing |

## Skill Structure

Each skill folder contains:

```
skill-name/
├── SKILL.md          # YAML frontmatter + markdown instructions
├── references/       # Supporting documentation (optional)
├── scripts/          # Helper scripts (optional)
├── templates/        # File templates (optional)
└── assets/           # Static assets (optional)
```

## Usage

These skills are designed for [Hermes Agent](https://hermes-agent.nousresearch.com/). To install:

```bash
# Clone to your Hermes profile skills directory
git clone https://github.com/peterlau123/skills-you-need.git
cp -r skills-you-need/* ~/.hermes/profiles/<profile>/skills/
```

## License

MIT
