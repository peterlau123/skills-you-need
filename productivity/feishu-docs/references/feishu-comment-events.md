# Feishu Comment Event Handling (Gateway Auto-Reply)

Verified 2026-08-17 from Hermes source code (`plugins/platforms/feishu/`) and
gateway logs on mx001, ai-engineer profile.

## Overview

The Hermes Feishu adapter auto-responds to document comments where the bot is
@mentioned. This is a gateway-side feature, separate from the manual API flow
for reading/replying to comments from a DM session.

## Architecture

```
Feishu websocket → adapter._on_drive_comment_event()
  → handle_drive_comment_event()  [feishu_comment.py]
    1. Parse event (file_token, comment_id, reply_id, from_open_id, to_open_id)
    2. Filter: self-reply / to_open_id == bot_open_id / notice_type
    3. Access control: resolve_rule() + is_user_allowed()
    4. If denied → log + return (no reaction, no reply)
    5. If allowed:
       a. Add OK reaction to the comment
       b. Parallel fetch: doc meta (batch_query) + comment details (batch_query)
       c. Build timeline (whole-doc comments OR local thread replies)
       d. Build prompt with timeline + quote + instructions
       e. Run AIAgent (model from gateway config, toolsets: feishu_doc + feishu_drive)
       f. Deliver reply (reply_to_comment OR add_whole_comment)
       g. Delete OK reaction
```

## Access-control config: `feishu_comment_rules.json`

**Location**: `get_hermes_home() / "feishu_comment_rules.json"`  
(profile-specific — e.g. `~/.hermes/profiles/ai-engineer/feishu_comment_rules.json`)

**Hot-reloaded**: mtime-cached, no restart needed.

### Full config format

```json
{
  "enabled": true,
  "policy": "allowlist",
  "allow_from": ["ou_755bfc83496581afd1b5e14204f06ace"],
  "documents": {
    "docx:LsPNdBQhuo6LD5xq6zjcSQ1hnAd": {
      "enabled": true,
      "policy": "allowlist",
      "allow_from": ["ou_..."]
    },
    "*": {
      "policy": "pairing"
    }
  }
}
```

### Policy values

| Policy | Behavior | When to use |
|---|---|---|
| `allowlist` | Only users in `allow_from` can trigger | Single-user or known-team setup |
| `pairing` | Users must be in `feishu_comment_pairing.json` approved list | Multi-user with approval flow |

### Rule resolution (field-by-field fallback)

```
exact doc (fileType:fileToken) → wiki key (wiki:nodeToken) → wildcard "*" → top-level → code defaults
```

Each field (`enabled`, `policy`, `allow_from`) falls back independently. The
`match_source` in logs tells you which tier contributed:

- `exact:docx:xxx` — exact document match
- `wildcard` — matched via `"*"` key
- `top` — fell through to top-level config
- `default` — no config file, code defaults applied

### Default when file is MISSING

```
CommentsConfig():
  enabled = True
  policy = "pairing"       # ← denies everyone without pairing file
  allow_from = frozenset()  # ← empty
```

This is the most common misconfiguration: the rules file doesn't exist, so
`policy=pairing` + empty `allow_from` + no pairing file = **all users denied**.

## Pairing store: `feishu_comment_pairing.json`

**Location**: `get_hermes_home() / "feishu_comment_pairing.json"`

```json
{
  "approved": {
    "ou_755bfc83496581afd1b5e14204f06ace": {
      "approved_at": 1723891200.0
    }
  }
}
```

Managed via CLI: `python -m plugins.platforms.feishu.feishu_comment_rules pairing add <open_id>`

## Event filtering

The handler drops events that fail any of these checks:

1. **Self-reply**: `from_open_id == self_open_id` (bot's own comments)
2. **Addressed to bot**: `to_open_id == self_open_id` (bot must be @mentioned)
3. **Notice type**: must be `add_comment` or `add_reply`
4. **Required fields**: `file_token`, `file_type`, `comment_id` must be non-empty

## Comment-agent execution

The agent that generates the reply runs with:

- **Model**: resolved from gateway config (`_resolve_model_and_runtime()`)
- **Toolsets**: `feishu_doc` + `feishu_drive` only
- **Max iterations**: 15
- **Quiet mode**: True (no streaming)
- **Skip memory/context files**: True (isolated execution)
- **Session cache**: per-document, keeps last 50 messages, 1-hour TTL
  - Key: `comment-doc:{file_type}:{file_token}`
  - Enables cross-card memory within the same document

## Reply delivery

- **Whole-document comment** (`is_whole=true`): `POST /drive/v1/files/{token}/new_comments`
- **Local comment** (`is_whole=false`): `POST /drive/v1/files/{token}/comments/{id}/replies`
  - Fallback: if reply returns `1069302` (not allowed), falls back to `add_whole_comment`
- **Chunking**: replies >4000 chars are split at line breaks

## Reaction lifecycle

1. On event arrival (if allowed): add `OK` emoji reaction to the comment
2. After agent completes (success or failure): delete the `OK` reaction
3. Reaction API: `POST /drive/v2/files/{file_token}/comments/reaction`
   - Body: `{"action": "add"/"delete", "reply_id": "...", "reaction_type": "OK"}`

## Gateway log diagnosis

Search `~/.hermes/profiles/<profile>/logs/gateway.log` for `Feishu-Comment`:

| Log pattern | Meaning | Action |
|---|---|---|
| `denied (policy=pairing, rule=top)` | Rules file missing or policy=pairing without pairing store | Create rules file with `policy: "allowlist"` |
| `denied (policy=allowlist, rule=...)` | User not in `allow_from` | Add user's open_id to `allow_from` |
| `handle_drive_comment_event START` | Event arrived and was parsed | Normal — check next lines for access granted/denied |
| `Access granted: user=...` | User passed access control | Reply should follow |
| No `Feishu-Comment` entries after restart | Events not arriving at all | Check Feishu console event subscription for `drive.notice.comment_add_v1` |
| `Dropping drive comment event before adapter loop is ready` | Event arrived during startup | Transient — should self-resolve |

## Event subscription (Feishu console)

The adapter registers for `drive.notice.comment_add_v1` via:

```python
.register_p2_customized_event(
    "drive.notice.comment_add_v1",
    self._on_drive_comment_event,
)
```

This is a **customized event** — it must be subscribed in the Feishu open
platform console under 事件与回调 → 事件订阅. If the subscription is missing
or was removed, no events will arrive even though the websocket is connected
and IM messages work fine.

## Source files

| File | Purpose |
|---|---|
| `plugins/platforms/feishu/feishu_comment.py` | Event handler, API calls, prompt building, agent execution |
| `plugins/platforms/feishu/feishu_comment_rules.py` | Config loading, rule resolution, pairing store, access check |
| `plugins/platforms/feishu/adapter.py` | Event registration (`register_p2_customized_event`), dispatch |

## Quick setup checklist

1. ✅ `feishu_comment_rules.json` exists with `policy: "allowlist"` and user's `open_id`
2. ✅ Bot app has `drive:drive` scope (read + write for comment APIs)
3. ✅ Bot is @mentioned in the comment (events without @mention are filtered)
4. ✅ Feishu console: event subscription includes `drive.notice.comment_add_v1`
5. ✅ Bot is a collaborator on the document (at least 可阅读)
6. ✅ Gateway websocket is connected (check `gateway.log` for "Connected in websocket mode")
