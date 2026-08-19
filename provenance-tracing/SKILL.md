---
name: provenance-tracing
description: Find where an IP/claim came from; verify what you said.
version: 1.0.0
author: Hermes Agent
license: MIT
platforms: [linux, macos]
---

# Provenance Tracing (where did X come from?)

Use when the user asks "where did this IP/hostname/claim come from?", "did you ever say X?", "who told you Y?", or challenges a fact attributed to you. Goal: answer with evidence, attribute the origin to a specific source (user message / assistant output / tool output / file / config), and never guess or fabricate.

## Golden rule
Never answer from memory or assumption — prove it from primary sources. The user's question may itself be based on a misremembering; verify what YOU actually said before accepting or denying anything.

## Step 1 — FTS5 session search (fast, but NOT exhaustive)
`session_search(query=...)` is a fine first pass, but has two blind spots:
- The FTS5 unicode61 tokenizer splits on punctuation (dots, slashes, colons). IP addresses (`10.10.192.55`), FQDNs, and version strings (`3.9.10`) do NOT match as phrase queries even when present in the DB.
- The default `role_filter='user,assistant'` excludes tool output.

→ **Zero results from session_search is NOT proof of absence.** Always confirm with Step 2.

## Step 2 — Raw DB search (definitive ground truth)
Locate the session DB (usually `~/.hermes/profiles/<profile>/state.db`) and search it raw:

```bash
find ~/.hermes \( -name "*.db" -o -name "*.sqlite*" \) 2>/dev/null
strings <state.db> | grep -c "<pattern>"   # 0 = truly absent; >0 = present somewhere
```

Then pin down the exact rows with Python sqlite3 (plain `LIKE`, NOT the FTS table):

```sql
SELECT m.id, m.session_id, m.role, m.tool_name, m.timestamp, substr(m.content,1,3000)
FROM messages m
WHERE m.content LIKE '%<pattern>%' OR m.tool_calls LIKE '%<pattern>%' OR m.reasoning LIKE '%<pattern>%'
ORDER BY m.timestamp;
```

Also scan `sessions` for title/source. **Crucial attribution step**: check `role` — if the only hits are `role='user'` messages, or assistant tool calls that merely echoed the user's text, then the origin is the user's own message, not something you said.

## Step 3 — Filesystem & config sweep
Grep the string in: the repo in question, `/etc/hosts`, `~/.ssh/config`, `~/.gitconfig`, env vars, `~/.hermes` configs.
CAUTION: `agent.log` / `gateway.log` echo inbound user messages — a hit in logs may just be the user's own text quoted back. Same for your own tool-output echo. Neither is evidence you originated it.

## Step 4 — Report with an attribution table
Present: scope checked | result (e.g. session DB, repo files, /etc/hosts, ssh config, git config, env, logs). State plainly who originated it (user vs assistant vs file). If the user is wrong ("you never said that", "it's in no config"), say so with the evidence and offer the likely real origin (another machine, another environment, another conversation) — don't let a false accusation stand, and don't invent a source to be agreeable.

## Pitfalls
- **FTS5 zero results ≠ absent** — Step 2 is the ground truth (see references/ip-address-case.md).
- A string found in your own tool outputs that quoted the user's message is a false positive for "assistant originated it".
- Don't stop at "the string exists in the DB" — identify the role of the message that FIRST introduced it.
- When the user asserts a capability difference ("direct access works", "that URL is reachable"), verify live with a probe rather than accepting or repeating stale claims — see `github-restricted-network-access` for the probe ladder.

## References
- `references/ip-address-case.md` — worked example: "where did 10.10.192.55 come from?" (answer: the user's own message; FTS5 missed it entirely).
