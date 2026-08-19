# Worked case: "where did 10.10.192.55 come from?"

User (Feishu, mx001 host) challenged: "你不需要访问10.10.192.55，你直接访问github即可，10.10.192.55信息是从哪里来的？" (You don't need 10.10.192.55 — access GitHub directly. Where did that info come from?)

Context: the assistant had just cloned peterlau123/ai-infra-wiki via `gh-proxy.com` (github.com direct is blocked on mx001). The IP was never used or mentioned by the assistant.

## Investigation sequence (what worked)

1. `session_search("10.10.192.55")` → 0 results. Repeated with `role_filter='user,assistant,tool'` → 0 results. **Misleading**: FTS5 tokenizes "10.10.192.55" into tokens {10,10,192,55} on the dots, so the phrase never matches. Lesson: FTS5 silence ≠ absence for IPs/versions/FQDNs.
2. `grep -rn` in the cloned repo → 0 hits.
3. `grep -rn` in /etc/hosts, ~/.ssh/config, ~/.gitconfig, env → 0 hits.
4. `grep -rn 10.10.192.55 ~/.hermes/` → hits ONLY in `logs/agent.log` and `logs/gateway.log`, and those lines were the platform adapter echoing the user's OWN inbound message. Log grep = false positive for "assistant said it".
5. Raw DB sweep: `find ~/.hermes -name "*.db"` → found `state.db` per profile. `strings state.db | grep -c 10.10.192.55` → 117 (profile ai-engineer). This is the definitive existence check.
6. Python sqlite3 on `~/.hermes/profiles/ai-engineer/state.db`, plain LIKE over `messages.content`/`tool_calls`/`reasoning` → exactly 7 rows:
   - 1 row: `role='user'` — the user's own question (the true origin).
   - 6 rows: my own investigation tool calls/results that echoed the user's text back.
7. Live network probe settled the second claim ("直接访问github即可"): `github.com → HTTP 000` (curl's code for connection failure/timeout), `codeload.github.com → 301`, `gh-proxy.com → 200`. Direct GitHub access is still broken on mx001; user was likely thinking of a different machine (H20 env).

## Outcome
Reported an attribution table (scope | result), stated the origin was the user's own message, and noted the direct-access claim doesn't hold on mx001 — verified with live evidence.

## Reusable commands
```bash
# definitive existence check across all profile DBs
for db in $(find ~/.hermes -name "*.db"); do echo "$db: $(strings "$db" | grep -c '<pattern>')"; done
```
```python
# locate exact rows + role attribution (see SKILL.md Step 2 for full SQL)
import sqlite3
con = sqlite3.connect("/home/ecs-user/.hermes/profiles/<profile>/state.db")
for m_id, role, ts, sess in con.execute("SELECT id, role, timestamp, session_id FROM messages WHERE content LIKE '%<pattern>%'"):
    print(m_id, role, ts, sess)
```
