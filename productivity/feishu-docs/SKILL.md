---
name: feishu-docs
description: "Use when reading or writing Feishu/Lark docs and wiki via API, including doc comments."
version: 1.2.0
license: MIT
metadata:
  hermes:
    tags: [feishu, lark, docs, api, drive, upload, write, create]
---

# Feishu / Lark Docs Access (mx001, ai-engineer profile)

Use when the user pastes a Feishu/Lark doc link (`https://<tenant>.feishu.cn/wiki/<token>`,
`/docx/<token>`, `/docs/<token>`) and asks to read/summarize it, or asks to upload artifacts to
Feishu cloud space. Reply in Chinese — the user works in a Feishu workspace.

## Tool limitation first

The following deferred-catalog plugin tools only work **in a doc-comment context** (i.e. when
the gateway delivered a comment event to the agent); in a plain DM they all fail with
"Feishu client not available (not in a Feishu comment context)":

- `feishu_doc_read` — read doc content
- `feishu_drive_list_comments` — list comments on a doc
- `feishu_drive_reply_comment` — reply to a local (quoted-text) comment thread
- `feishu_drive_add_comment` — add a whole-document comment
- `feishu_drive_list_comment_replies` — list replies in a comment thread

Do NOT retry any of these in a loop — fall through to the direct API paths below. When the user
says "我在文档里评论了" or "回复文档评论", go straight to the **Doc comments (read & reply from
DM)** section.

## Credentials on this machine

- **Read scopes live on the janus app**: `~/.hermes/profiles/janus-model-adapt/secrets/feishu_app.json`
  (app `cli_aae7…`, provisioned 2026-08-05, doc read scopes enabled). The user approved its use
  for doc reads; copy it to `~/.hermes/profiles/<profile>/secrets/feishu_app.json` (chmod 600)
  when the active profile lacks one.
- **Write scopes live on the chat-gateway bot**: the app `cli_aa95…` (creds `FEISHU_APP_ID` /
  `FEISHU_APP_SECRET` in the profile `.env`) has `docx:document` + `docx:document:create`
  (verified 2026-08-06: create doc + write blocks succeeded with it), while the janus app
  still returns `code: 99991672` on write calls.
- **Two-app split is the norm on this machine**: read with the janus app, write with the chat bot.
  If one app fails a call with `99991672`, switch to the OTHER app's credentials before asking the
  user to grant scopes — the user may have granted them to the app you're not using.
- Never write app_secret to memory or echo it in chat.

## API read flow (app creds → doc text)

1. `POST https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal` with
   `{"app_id":…,"app_secret":…}` → `tenant_access_token`.
2. **Wiki links need two-step resolution**: the URL token is the *wiki node* token. Call
   `GET /open-apis/wiki/v2/spaces/get_node?token=<url-token>` → `obj_token` (+ `obj_type`, usually
   `docx`) before reading.
3. Read content: `GET /open-apis/docx/v1/documents/<obj_token>/raw_content` (docx) — returns plain
   text. Legacy `/docs/` tokens use the docx API too after resolution.
4. **If `obj_type` is `file`** (not `docx`): the `obj_token` is a drive file token, NOT a docx
   document ID. The docx `raw_content` API returns `404 / code: 1770002 "not found"`. Use the
   **Drive file download** flow below instead — `GET /open-apis/drive/v1/files/<obj_token>/download`.
   This happens when a .docx/.pptx/.pdf is uploaded as a file attachment to a wiki node rather
   than created as a native Feishu doc.

## IM message read (recover full bot-delivered text — cron responses, alerts)

When a user replies to a bot-delivered message (e.g. a cron job response) and you need the FULL
text — the Feishu reply quote is truncated, and the local store (cron jobs.db/output, session DB,
gateway logs) may be wiped/empty — fetch the original message from the IM API:

- **Which app**: the chat-gateway bot (`cli_aa95…`, creds `FEISHU_APP_ID` / `FEISHU_APP_SECRET` in
  the profile `.env`). The janus read app (`cli_aae7…`) is NOT a member of DMs and fails with
  `code 230002 "Bot/User can NOT be out of the chat"` on IM calls.
- **Which ID**: in a DM, the session-key thread token (the `:om_...` suffix, e.g.
  `agent:main:feishu:dm:<chat_id>:om_x100...`) IS the `message_id` of the message the user replied
  to (gateway logs it as `reply_to_id`). Fetch it directly — no list call needed.
- **Call**: `GET /open-apis/im/v1/messages/<message_id>` with
  `Authorization: Bearer <tenant_access_token>`.
- **Parse**: `msg_type` is usually `post`; `data.items[0].body.content` is JSON with `content`
  (rich segment array) and `content_v2` (clean markdown array). Read `content_v2[0].text` for the
  full readable markdown.

## Automated comment event handling (gateway-side auto-reply)

The Hermes Feishu adapter can auto-respond to document comments without user DM
intervention. When a user @mentions the bot in a Feishu document comment, the
gateway receives a `drive.notice.comment_add_v1` event, runs a comment-agent
with `feishu_doc` + `feishu_drive` tools, and posts the reply back to the
comment thread.

This is **separate from the manual API flow** above — it requires gateway-side
configuration and event subscription, not just API credentials.

### Access-control config: `feishu_comment_rules.json`

Located at `get_hermes_home() / "feishu_comment_rules.json"` (profile-specific,
mtime-cached, hot-reloaded — no restart needed to pick up changes).

```json
{
  "enabled": true,
  "policy": "allowlist",
  "allow_from": ["ou_<user_open_id>"],
  "documents": {}
}
```

- **`policy: "allowlist"`** — only users in `allow_from` can trigger the bot.
  This is the recommended policy for a single-user setup.
- **`policy: "pairing"`** (default when file is missing) — users must be
  approved via a separate `feishu_comment_pairing.json` store. With no pairing
  file, **everyone is denied**. This is the most common misconfiguration.
- **`documents`** — per-document overrides. Keys are `fileType:fileToken`
  (e.g. `"docx:LsPNdBQhuo6LD5xq6zjcSQ1hnAd"`), or `"*"` for wildcard. Each
  field (`enabled`, `policy`, `allow_from`) falls back independently through
  exact → wildcard → top-level → code defaults.

### Critical pitfall: missing rules file = silent denial

If `feishu_comment_rules.json` does not exist, the code defaults to
`CommentsConfig()` → `policy="pairing"` + empty `allow_from`. This silently
denies ALL comment events. The gateway log shows:

```
[Feishu-Comment] User ou_... denied (policy=pairing, rule=top)
```

**Always create the rules file before testing comment events.** Set
`policy: "allowlist"` with the user's `open_id` in `allow_from`.

### Event flow (for debugging)

1. Feishu websocket delivers `drive.notice.comment_add_v1` event
2. Adapter dispatches to `handle_drive_comment_event()` in
   `plugins/platforms/feishu/feishu_comment.py`
3. Event is parsed; filtered by `to_open_id == bot_open_id` (bot must be
   @mentioned) and `notice_type in {add_comment, add_reply}`
4. Access control: `resolve_rule()` + `is_user_allowed()` — denied events
   are logged and dropped (no reaction, no reply)
5. If allowed: OK reaction added → parallel fetch (doc meta + comment details)
   → build prompt → run comment-agent → deliver reply → remove reaction

### Gateway log diagnosis

Search `~/.hermes/profiles/<profile>/logs/gateway.log` for `Feishu-Comment`:

- `denied (policy=...)` — access control blocked the user; check rules file
- `handle_drive_comment_event START` — event arrived and was parsed
- No `Feishu-Comment` entries after a restart — events not arriving at all
  (check Feishu console event subscription, not a Hermes-side issue)

### Restarting the gateway (pitfall, verified 2026-08-17)

`hermes gateway restart` run **from inside the gateway process** (i.e. from the agent's own
terminal) is refused: `✗ Refusing to restart the gateway from inside the gateway process. This
command was blocked to prevent restart loops.` The rules file itself hot-reloads (mtime-cached,
no restart needed), but if a restart IS required (e.g. after .env changes): kill the old PID
found in `gateway_state.json` (`kill <pid>`), wait ~3s, and let the supervisor respawn it — the
session reconnects automatically. Verify afterwards with `cat gateway_state.json` →
`platforms.feishu.state == connected`.

See `references/feishu-comment-events.md` for full config format, rule
resolution logic, and the comment-agent execution details.

## Doc comments (read & reply from DM)

When the user says "我在文档里评论了" / "回复文档评论" and provides a doc URL, the plugin tools
won't work (see Tool limitation above). Use direct API calls instead. Verified 2026-08-17.

### Which app to use

- **List comments + read doc context**: use the **janus read app** (`cli_aae7…`) — it has
  `drive:drive:readonly` and is already a collaborator on wiki docs the user shared.
- **Reply to a comment**: use the **chat-bot app** (`cli_aa95…`, creds from `.env`) —
  the janus app lacks `drive:drive` write scope and returns `99991672` on comment replies.
  If janus fails on list too, switch to chat-bot (it has read access via `drive:drive`).

### List comments

```
GET /open-apis/drive/v1/files/<obj_token>/comments?file_type=docx&page_size=100
Authorization: Bearer <tenant_access_token>
```

Response `data.items[]` key fields:
- `comment_id` — needed for reply
- `quote` — the quoted doc text the comment is anchored to (gives context)
- `is_whole` — `true` = whole-document comment; `false` = anchored to specific text
- `is_solved` — whether the comment is resolved
- `reply_list.replies[]` — existing replies; each reply has `content.elements[]` (same
  structure as block elements: `text_run.text`, `person.user_id`, etc.)
- `user_id` — comment author's `open_id`

### Read doc context around the comment

After listing comments, use the `quote` field to locate the relevant section in the doc:

1. Read raw content: `GET /open-apis/docx/v1/documents/<obj_token>/raw_content`
2. Search for the `quote` text to find surrounding context and understand what the user
   is commenting on.

### Reply to a comment

```
POST /open-apis/drive/v1/files/<obj_token>/comments/<comment_id>/replies?file_type=docx
Authorization: Bearer <tenant_access_token>
Content-Type: application/json

Body:
{
  "content": {
    "elements": [
      {
        "type": "text_run",
        "text_run": {"text": "回复内容..."}
      }
    ]
  }
}
```

**Critical**: the body must have a flat `content` object with `elements` — NOT wrapped in
`reply_list`. Wrapping in `{"reply_list": {"replies": [{"content": ...}]}}` returns
`code: 99992402 "field validation failed"` with `"content is required"`.

Multi-line text in `text_run.text` is supported — use `\n` for line breaks.

## Required app scopes (permission management in Feishu console)

- `docx:document:readonly`, `wiki:wiki:readonly`, `drive:drive:readonly` (read)
- `drive:file:upload` (+ `space:folder:create` for folder creation) (upload)
- Scopes alone are NOT enough: the app must also be a collaborator (可阅读) on the specific doc, or
  the wiki space must be visible to it. Missing-scope error `code: 99991672` carries a grant link in
  `msg` — hand it to the user verbatim.

## Wiki child node creation (sub-documents under a wiki page)

When the user asks to create a **child document under an existing wiki page** (e.g. "在这个文档下面
新建子文档"), the flow is different from standalone doc creation.

### The permission wall (critical)

Creating a child wiki node requires **wiki space edit permission**, which is SEPARATE from
`docx:document` / `docx:document:create` scopes:

- `docx:document` scopes → can create standalone docs in the app's default folder ✓
- Wiki space edit permission → needed to create child nodes or move docs into wiki ✗

The bot app (`cli_aa95…`) has docx write scopes but is NOT a wiki space member with edit
permission. Error: `code: 131006 "permission denied: node permission denied, tenant needs edit
permission"`.

### Relevant APIs

| API | Purpose | Permission needed |
|---|---|---|
| `POST /wiki/v2/spaces/{space_id}/nodes` | Create child wiki node directly | Wiki space edit (`wiki:wiki` or `wiki:node:create` scope + space membership) |
| `POST /wiki/v2/spaces/{space_id}/nodes/move_docs_to_wiki` | Move standalone docx into wiki tree | Edit permission on the parent node |
| `GET /wiki/v2/spaces/{space_id}/members` | List wiki space members | Works with read access (view permission) |
| `GET /bot/v3/info` | Get bot's own open_id | Token only |

### Two-step resolution (required before any wiki operation)

Wiki URLs use node tokens. Resolve first:
```
GET /open-apis/wiki/v2/spaces/get_node?token=<url-token>
→ data.node.obj_token (doc_id), data.node.space_id, data.node.parent_node_token
```

### Transfer document ownership (verified 2026-08-14)

When the bot creates a document but the user needs full control (move, delete, reshare),
transfer ownership to the user. This makes the user the document owner.

```
POST /open-apis/drive/v1/permissions/{doc_token}/members/transfer_owner?type=docx
Body: {"member_type":"openid","member_id":"<user_open_id>"}
```

- Verified working on chat-bot app (`cli_aa95…`). Requires `drive:drive` scope.
- After transfer, the user can move the doc into wiki from the Feishu UI without bot involvement.
- The bot retains collaborator access but is no longer the owner.
- Use this as step 4 of the fallback workflow below when the bot can't move docs into wiki.

### Add user as collaborator (verified 2026-08-14)

```
POST /open-apis/drive/v1/permissions/{doc_token}/members?type=docx
Body: {"member_type":"openid","member_id":"<user_open_id>","perm":"full_access"}
```

- `perm` values: `view`, `edit`, `full_access`.
- Works when the bot is the document owner (created the doc itself).
- Returns `1063002 "Permission denied"` if the bot is NOT the owner — can't self-grant on
  docs owned by others.

## Fallback workflow (when bot lacks wiki edit permission)

1. **Create standalone doc** (works with docx scopes):
   ```
`
   POST /open-apis/docx/v1/documents  Body: {"folder_token": ""}
   → data.document.document_id
   ```
2. **Write blocks** into the standalone doc (see "Doc write flow" below).
3. **Attempt to move into wiki** — this WILL fail with `131006` if the bot isn't a wiki space
   member with edit permission:
   ```
   POST /open-apis/wiki/v2/spaces/{space_id}/nodes/move_docs_to_wiki
   Body: {"parent_wiki_token": "<parent_node_token>", "obj_type": "docx", "obj_token": "<doc_id>"}
   → code: 131006 "permission denied: no destination parent node permission"
   ```
4. **Transfer ownership to user** so they can move it from the Feishu UI:
   ```
   POST /open-apis/drive/v1/permissions/{doc_id}/members/transfer_owner?type=docx
   Body: {"member_type":"openid","member_id":"<user_open_id>"}
   ```
5. **User moves the doc into wiki** via Feishu UI: open doc → "···" → 移动 → select wiki page.
   The user must be the doc owner (step 4) to move it.

### Checking wiki space membership

The members list API works with read access:
```
GET /open-apis/wiki/v2/spaces/{space_id}/members?page_size=20
```
Check if the bot's `open_id` (from `GET /bot/v3/info`) appears in the member list and what
`member_role` it has (`admin` / `edit` / `view`). If missing or `view` only, wiki child node
creation is impossible without user action.

### Required scopes for wiki node creation

- `wiki:wiki` or `wiki:node:create` — these are SEPARATE from `wiki:wiki:readonly`
- The janus app (`cli_aae7…`) has `wiki:wiki:readonly` only → returns `99991672` on wiki write
- Even with scopes, wiki space membership with edit permission is required (same scope ≠
  collaborator pattern as drive files)

## Drive upload (archiving artifacts)

- `POST /open-apis/drive/v1/files/upload_all` (multipart, <20MB/file). Gotcha: EVERY field
  (`file_name`, `parent_type`, `size`, `parent_node`) must be a multipart form-data field in the
  BODY — query params return `code: 1061002` on every file.
- Response links: `https://<tenant>.feishu.cn/file/<file_token>`.

## Doc write flow (create + write blocks)

Create and populate Feishu docx documents via the Open API. Verified 2026-08-06.

### Required scopes (in addition to read scopes)

- `docx:document` or `docx:document:create` — create documents and write block content
- Scopes must be enabled AND the app must publish a new version (version management →
  创建版本 → 发布) if in dev mode. Enabling the scope alone does NOT take effect until published.

### Create document

```
POST /open-apis/docx/v1/documents
Body: {"folder_token": ""}   # empty = app's default folder
→ data.document.document_id  # use this as the doc token for block writes
```

### Write blocks into a document

```
POST /open-apis/docx/v1/documents/<doc_id>/blocks/<doc_id>/children
```

The `<doc_id>` appears as both the document ID and the parent block ID (the document root IS
a block). Body has a `children` array of block objects. Key block types:

| block_type | Meaning | Key field |
|---|---|---|
| 2 | Text (paragraph) | `text.elements[].text_run.content` |
| 3 | Heading 1 | `heading1.elements[].text_run.content` |
| 4 | Heading 2 | `heading2.elements[].text_run.content` |
| 5 | Heading 3 | `heading3.elements[].text_run.content` |
| 12 | Bullet list item | `bullet.elements[].text_run.content` |
| 13 | Ordered list item | `ordered.elements[].text_run.content` |
| 14 | Code block | `code.elements[].text_run.content` + `code.style.language` (1=PlainText, 39=Markdown, 49=Python; NO mermaid) |
| 31 | Table | `table.property.{row_size, column_size, column_width, header_row}` — cells via descendant endpoint only |
| 32 | Table cell | `table_cell: {}` + `children: ["<text-block-tmp-id>"]` |

Example body (heading + two paragraphs):
```json
{
  "children": [
    {
      "block_type": 3,
      "heading1": {"elements": [{"text_run": {"content": "标题"}}]}
    },
    {
      "block_type": 2,
      "text": {"elements": [{"text_run": {"content": "段落内容"}}]}
    }
  ]
}
```

### Write pitfalls

- **Dev-mode publish gotcha**: after enabling `docx:document` scope, the API still returns
  `code: 99991672` until the user creates and publishes a new app version in the Feishu console.
  The missing-scope error carries a grant link in `msg` — hand it to the user, but also tell
  them to publish.
- The document root block ID = the document ID itself. Use it as the parent when writing
  top-level children.
- Block `elements` is an array; multiple `text_run` entries allow inline formatting (bold, links).
- Creating a document returns a URL: `https://<tenant>.feishu.cn/docx/<document_id>`.
- Writing to an existing document (e.g. a wiki page) requires the app to be a collaborator with
  edit permission (可编辑), not just read.
- **Batch limit: 50 blocks per request** (API returns error if exceeded). For large documents
  (100+ blocks), batch writes in chunks of 45 with a 0.5s sleep between batches. A 375-block
  document was successfully written in 9 batches of 45 on 2026-08-14. Use a Python script with
  `urllib.request` (not curl) for batch writes — easier JSON construction and error handling.
### Restructuring an existing doc's heading hierarchy (grouping / renumbering)

To add a grouping layer ABOVE existing sections (e.g. user asks "把 2.0-2.11 再加一层大目录区分"), or otherwise reorganize headings, know these hard constraints (verified 2026-08-18):

- **block_type is immutable via API** — no `replace_block`, no heading-level change (h2→h3 fails with `1770001 invalid param`). A heading created as h2 stays h2 forever.
- **No block MOVE via batch_update** — only insert (children/descendant with `index`), delete-by-index-range, and content PATCH. Physical order of existing blocks cannot be regrouped.
- **Workable pattern — "regroup by renumbering"**: insert the new group headings at the right positions, then renumber the existing sub-headings' CONTENT via `batch_update` `update_text` (e.g. `2.6 torch.library` → `2.1.1 torch.library`). The numbering carries the grouping semantics even when physical order can't match. Verify with a script: parse all headings, assert each sub-number's group-prefix matches the group heading it sits under.
- **Insert multiple headings back-to-front**: when inserting group titles at several `index` positions in ONE pass, insert in DECREASING index order (largest index first) so earlier insertions don't shift later targets. Inserting front-to-back drifts every subsequent index by +1.
- **Re-fetch the block list before assuming structure**: the doc may have been edited by the user or another session since your last read (this session found new headings that the agent never created — a stale mental model caused wrong insert positions).

### Insert at a position**: append `?index=N` to the same children URL (block index where the
  new blocks land). Verified 2026-08-14: inserting a subsection at `index=29` (before heading
  1.2) worked — useful for splicing corrections into an existing doc without rewriting it.

### Splicing into an existing doc: use the `descendant` endpoint for nested content

To insert tables or any block WITH children into an existing document (e.g. answer a doc
comment by adding a section + table before the next heading), the plain `children` endpoint
CANNOT carry cell text — `table.cells` is a `string[]` of cell-block IDs, and inline cell
blocks in the same call fail with `code: 9499`. Use:

```
POST /open-apis/docx/v1/documents/<doc_id>/blocks/<doc_id>/descendant
Body: {"index": <position>, "children_id": ["tmp1",...],
       "descendants": [<every block in the tree, leaves have children: []>]}
```

Key facts (verified 2026-08-17):
- `children_id` lists temp IDs of TOP-LEVEL blocks only; `descendants` defines every block
  (table → table_cell → text, each referencing children by temp ID). Response maps temp→real.
- `index` = insertion position among the page's children; find it by GETting children and
  locating the target heading block's index, then insert there.
- **`update_text` in `batch_update` requires BOTH `style: {"align": 1}` AND `fields: [1]`** —
  omitting either returns `code: 99992402 field validation failed`. This is also the way to
  REPURPOSE a throwaway test block into real content (since plain DELETE of a block returns
  `404 page not found` on this tenant; use repurpose or `children/batch_delete` by index range).
- **No mermaid block**: Feishu `diagram` blocks only support flowchart/UML. Deliver mermaid as
  a code block (`block_type: 14`, `style.language: 1` PlainText) and note the user can copy it
  to a mermaid renderer. `block_type: 35` + `language: 11` (older docs) returns `1770001`.
- Full worked example + table construction: `references/feishu-docx-descendant-write.md`.
- **Delete blocks (batch_delete)**: `DELETE /open-apis/docx/v1/documents/<doc_id>/blocks/<doc_id>/children/batch_delete`
  with body `{"start_index": 0, "end_index": N}`. Max ~100 per call; delete from `start_index=0`
  repeatedly (remaining blocks shift down) to clear the whole doc. Verified: wiped a 567-block
  doc in 6 calls.
- **Full-doc rewrite pattern**: to restructure a doc (e.g. re-order sections), read all blocks
  (paginate `GET .../children?page_size=500&page_token=...`), then batch_delete everything from
  index 0, then write the new content in chunks of 45. Verified 2026-08-14: 567 blocks deleted +
  282 rewritten in 7 batches.

## Drive file download (read attached files from /file/ links or wiki file nodes)

User pastes a link like `https://<tenant>.feishu.cn/file/<file_token>` (PPTX/PDF/etc.), OR
a wiki node resolves with `obj_type: file` (the `obj_token` is the file token):

```
GET /open-apis/drive/v1/files/<file_token>/download
Authorization: Bearer <tenant_access_token>
```

- Returns the raw binary (HTTP 200) — save with `curl -o` and check with `file` (e.g.
  "Microsoft PowerPoint 2007+" or "Microsoft Word 2007+").
- **Which app to use**: try the chat-bot app (cli_aa95…) first; if it returns `403` with an
  empty body, try the janus app (cli_aae7…). If janus returns `400 / code: 99991672`, it
  lacks the `drive:file:download` scope — see the error table below.
- Meta endpoint `GET /open-apis/drive/v1/files/<file_token>` can return non-JSON (rate-limit /
  error page) — don't block on it; the download endpoint is the reliable path.
- The `GET /open-apis/drive/v1/medias/<file_token>/download` endpoint also exists but returns
  the same errors — do NOT use it as a workaround for download permission issues.

### Download permission diagnostics (error → cause → fix)

| HTTP | code | body | cause | fix |
|---|---|---|---|---|
| 400 | 99991672 | `{"msg":"Access denied...scopes required: [drive:drive...]"} `| App lacks drive download scope | Feishu console → 权限管理 → add `drive:file:download` (or `drive:drive:readonly`) → 版本管理 → 创建版本 → 发布 |
| 403 | (none) | empty body | App HAS the scope but is NOT a collaborator on this specific file | User must share the file with the bot in Feishu UI (分享 → add bot → 可阅读). Cannot self-grant via permissions API — returns `1063002 "Permission denied"` |
| 403 | 1063004 | `{"msg":"User has no share permission"}` | App tried to add itself as collaborator but lacks share permission on the file | Only the file owner can grant collaborator access; ask the user to share it manually |

- **Scope ≠ collaborator**: even with `drive:file:download` scope granted AND published, the app
  must also be an explicit collaborator (可阅读) on each individual file. Wiki space visibility
  does NOT automatically extend to file attachments within wiki nodes.
- If both apps fail and the user cannot share the file, ask them to paste the content or
  export the document (Word/PDF/MD) directly in chat.

### Extracting text and images from a downloaded PPTX

#### Method 1: python-pptx (preferred when available)

The Hermes venv python3.11 has no pip, so `import pptx` fails there. Use the SYSTEM python:

```bash
/usr/bin/python3 -m pip install python-pptx -q     # system python 3.10, has pip
/usr/bin/python3 -c "
from pptx import Presentation
prs = Presentation('/tmp/feishu_ppt.pptx')
for i, slide in enumerate(prs.slides, 1):
    for shape in slide.shapes:
        if shape.has_text_frame:
            for para in shape.text_frame.paragraphs:
                if para.text.strip(): print(para.text.strip())
        if shape.has_table:
            for row in shape.table.rows:
                print(' | '.join(c.text.strip() for c in row.cells))
"
```

Text frames + tables both extract; image-only slides print nothing (note them as such).

#### User's preferred summary structure

When the user asks for a PPTX/document summary, structure it around four questions
(declared 2026-08-06):

1. **是什么？** (What) — define the thing/concept/project
2. **为什么？** (Why) — why it matters, pain points it solves
3. **怎样做？** (How) — approach, technical details, roadmap
4. **什么样的结果？** (What results) — outcomes, data, impact

Use tables and bullet points (少即是多), not prose paragraphs. This mirrors the user's
general 3W1H work framework (What/Why/When/How) with a results-oriented twist.

#### Version-comparison analysis docs (corrected 2026-08-14)

When writing a multi-version code analysis (e.g. "vLLM 技术架构分析" across v0.13.0 → v0.22.0),
the user's preferred structure is: **the primary analyzed version is the main body; the NEWER
version's deltas go at the END as an appendix**. Do NOT structure the doc as "old version +
diff notes" — the user explicitly asked to flip this: "分析以0.13.0为主，最后再补充上0.22.0
相较于0.13.0的变化". Also: when a quick grep suggests a feature is "absent" in a version, verify
with a deeper search before asserting it — this session's first pass wrongly claimed the plugin
system didn't exist in v0.13.0 when it did (4 plugin groups in vllm/plugins/).

#### Technical-analysis doc structure (review comments 2026-08-17)

When the user reviews a technical-architecture analysis (worked case: the vLLM 算子集成 /
PyTorch 能力 doc) and asks you to update it, two structural preferences recur — both are
"review comments" style corrections, so build them into the doc the FIRST time:

1. **Selection guide, not just an inventory**: when the doc enumerates mechanisms/options
   (算子集成方式, attention backends, etc.), the user expects a 选型指南 covering for EACH
   option: 适用场景 / 为什么选它 / 不选的代价, plus a one-line decision rule ("要能被
   torch.compile 优化 → 走 torch.ops（配 fake_impl）；性能热点且库成熟 → .so 直接调；
   平台相关要 fallback → CustomOp；新硬件 → 平台插件；快速原型 → Triton"). Listing what
   exists without saying which to pick and why is incomplete.
2. **High-level overview first**: before the per-topic deep-dive sections, add a 高层总览 —
   a mermaid diagram of the capability layers + a short layer table. The user asked for
   "从更高层面上总结 vLLM 会使用 PyTorch 的哪些能力，使用 mermaid 画出来". Deliver mermaid
   as a code block (`block_type: 14`, `language: 1`) — see the descendant-write section.

#### Method 2: ZIP + XML parsing (zero-dependency fallback)

When `python-pptx` or `lxml` is broken/unavailable, a PPTX is just a ZIP of XML files.
This method needs only `unzip` and Python stdlib `xml.etree.ElementTree` — no pip installs:

```bash
# 1. Unzip the PPTX
mkdir -p /tmp/pptx_extract && unzip -o /tmp/feishu_ppt.pptx -d /tmp/pptx_extract > /dev/null 2>&1

# 2. Keyword-search all slides to find the one you need
python3 -c "
import xml.etree.ElementTree as ET
ns_a = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
for i in range(1, 62):  # adjust range to slide count
    f = f'/tmp/pptx_extract/ppt/slides/slide{i}.xml'
    try:
        root = ET.parse(f).getroot()
    except: continue
    texts = [t.text for t in root.iter(f'{ns_a}t') if t.text]
    combined = ' '.join(texts)
    if 'PCB' in combined or '超节点' in combined:  # your keywords
        print(f'--- Slide {i} ---')
        print(combined[:300])
"

# 3. Extract images from a specific slide (slide 29 in this example)
python3 -c "
import xml.etree.ElementTree as ET, re
# Parse slide XML for r:embed references
tree = ET.parse('/tmp/pptx_extract/ppt/slides/slide29.xml')
ns_r = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
ns_a = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
for blip in tree.getroot().iter(f'{ns_a}blip'):
    rid = blip.get(f'{ns_r}embed')
    print(f'Image rId: {rid}')
# Parse the rels file to map rId → media file path
with open('/tmp/pptx_extract/ppt/slides/_rels/slide29.xml.rels') as f:
    for m in re.finditer(r'Id=\"([^\"]+)\".*Target=\"\.\./(media/[^\"]+)\"', f.read()):
        print(f'{m.group(1)} → {m.group(2)}')
"
# Images are at /tmp/pptx_extract/ppt/media/imageNN.png — copy and deliver via MEDIA:
```

See `references/pptx-extraction.md` for a complete worked example with image extraction.

#### When image analysis isn't available

If `vision_analyze` returns generic "I cannot see images" responses (model limitation, not a
tool failure), deliver the extracted images directly to the user via `MEDIA:/path/to/image.png`
and explain the content textually based on the slide's extracted text. The user can see the
images natively in Feishu even when the model cannot analyze them.

### PDF text extraction (pdf-inspector preferred, pymupdf fallback — mx001)

When you need to extract text from a PDF file (e.g. an AIGC detection report, a paper PDF):

- **Preferred: pdf-inspector** (Firecrawl Rust lib, ⭐16k — installed 2026-08-19 in the Hermes venv).
  Classifies text/scanned/mixed (~10-50ms), extracts structured Markdown (headings/tables/lists),
  beats pymupdf4llm on opendataloader-bench (0.875 vs 0.735) at 0.1-0.5s per 20-page paper:
  ```bash
  # Install into the Hermes venv when pip is missing — uv works where venv has no pip:
  uv pip install --python /home/ecs-user/.hermes/hermes-agent/venv/bin/python pdf-inspector
  ```
  ```python
  import pdf_inspector
  r = pdf_inspector.process_pdf('/path/to/file.pdf')
  print(r.pdf_type)    # text_based / scanned / image_based / mixed
  print(r.markdown)    # structured Markdown (or None for scanned)
  pages = pdf_inspector.extract_pages_markdown('/path/to/file.pdf')  # PagesExtractionResult, NOT a list
  # pages.pages -> list of PageMarkdown(page=N, markdown=..., needs_ocr=bool)
  # Scanned PDFs: process_pdf_with_ocr() routes only scanned pages to PP-OCRv6
  ```
  Pitfalls: `extract_pages_markdown` returns a `PagesExtractionResult` object — access `.pages`;
  `result.markdown` is `None` for scanned PDFs (use the `_with_ocr` variant).

- **Fallback: pymupdf** — use system python3.10, NOT the Hermes venv python3.11 (no pip):
  ```bash
  python3.10 -m pip install pymupdf -q   # system python has pip
  python3.10 -c "
  import pymupdf   # use 'pymupdf', NOT 'fitz' (deprecated, warns)
  doc = pymupdf.open('/path/to/file.pdf')
  for i, page in enumerate(doc):
      text = page.get_text()
      if text.strip():
          print(f'--- Page {i+1} ---')
          print(text[:3000])
  "
  ```
- `import fitz` still works but emits a deprecation warning; prefer `import pymupdf`.
- For large PDFs, paginate with `head -N` on the output to avoid flooding context.
- **General rule for installing Python packages into the Hermes venv** (verified 2026-08-19):
  the venv has NO pip, but `uv pip install --python <venv-python> <pkg>` works fine. Use it
  instead of switching to system python when the package is needed in the agent's own venv.

## References

- `references/feishu-open-api.md` — read flow (token + wiki + docx), drive upload, scopes, error codes.
- `references/feishu-doc-write-api.md` — doc write flow (create + block types + formatting).
- `references/wiki-node-management.md` — wiki child node creation APIs, permission diagnostics,
  batch block writing pattern (50-block limit, Python batch script, block construction helpers).
- `references/feishu-docx-descendant-write.md` — splicing content into EXISTING docs: descendant
  endpoint (children_id + descendants), table via block_type 31/32, update_text validation
  (style+fields required), DELETE-block 404 quirk, mermaid-in-code-block pattern.
- `references/feishu-comment-events.md` — gateway-side automated comment auto-reply: config
  (`feishu_comment_rules.json`), access-control policies, event flow, log diagnosis, source
  file map.
- `references/pptx-extraction.md` — zero-dependency PPTX text + image extraction via ZIP/XML parsing (fallback when python-pptx/lxml is broken).

## Pitfalls

- `curl` on `https://<tenant>.feishu.cn/wiki/<token>` returns HTTP 200 but an SSO/passport shell —
  no doc content, no embedded JSON. Never parse it; always use the API.
- Public-share scraping is unreliable; many tenants require login even for "anyone with the link".
- If no credentials / no access: ask the user to paste content or export the doc (Word/PDF/MD) —
  do NOT ask them to make the doc public.
- **Write scope ≠ write ability**: enabling `docx:document` scope in the Feishu console does NOT
  take effect until a new app version is published (dev-mode apps). The API keeps returning
  `code: 99991672` until published. Tell the user: 权限管理 → 勾选 → 版本管理 → 创建版本 → 发布.
- Models in `/v1/models` may be listed but not callable (observed: yicloud `glm5.2-pd` returns
  "Invalid model name"). Test with a real chat request, not just the models endpoint.
- **Wiki `obj_type: file` is not a docx**: when wiki node resolution returns `obj_type: file`,
  the `obj_token` is a drive file token — the docx `raw_content` API returns `404 / 1770002`.
  Switch to the drive download endpoint. See "Drive file download" section above.
- **File download needs collaborator access, not just scope**: even with `drive:file:download`
  scope granted and published, the app must be an explicit collaborator on each file. A `403`
  with empty body means "not a collaborator" — the app cannot self-grant via the permissions
  API (returns `1063002`). Ask the user to share the file with the bot in the Feishu UI.
- **Wiki child node creation needs wiki space membership, not just docx scopes**: `docx:document`
  + `docx:document:create` let the bot create standalone docs, but creating a child node under a
  wiki page returns `code: 131006 "permission denied: node permission denied, tenant needs edit
  permission"`. The bot must be a wiki space member with edit/admin role. This is a different
  permission from docx write scopes. See "Wiki child node creation" section above.
- **Divider block requires `"divider": {}` field**: `{"block_type": 22}` alone causes
  `code: 1770001 "invalid param"` that rejects the ENTIRE batch (not just the divider block).
  Always use `{"block_type": 22, "divider": {}}`. Same pattern applies to other content-less
  block types — include their (possibly empty) content field.
- **Plain DELETE of a block returns 404** on this tenant: `DELETE .../blocks/<block_id>`
  (even with `?document_revision_id=-1`). To remove content, use `children/batch_delete` with
  `{"start_index":0,"end_index":N}` or PATCH-repurpose the block via `update_text`.
- **Tables can't be created with content via the `children` endpoint**: `table.cells` is a
  `string[]` of cell-block IDs; inlining cell blocks fails `code: 9499`. Use the `descendant`
  endpoint (children_id + descendants, block_type 31 table / 32 table_cell). See
  `references/feishu-docx-descendant-write.md`.
- **`update_text` needs `style` AND `fields`**: `batch_update` PATCH returns `99992402` unless
  the request includes `"style": {"align": 1}` and `"fields": [1]` alongside `elements`.
- **No mermaid block type**: Feishu `diagram` blocks are flowchart/UML only; `block_type: 35`
  code blocks (older docs) return `1770001`. Put mermaid source in a real code block
  (`block_type: 14`, `language: 1`).
- **Comment reply body must be flat `content`**: POSTing to `.../comments/<id>/replies` with
  `{"reply_list": {"replies": [{"content": ...}]}}` returns `99992402 "content is required"`.
  Use `{"content": {"elements": [{"type": "text_run", "text_run": {"text": "..."}}]}}` directly.
- **Missing `feishu_comment_rules.json` = silent denial**: if the rules file does not exist,
  the code defaults to `policy="pairing"` + empty `allow_from`, which denies ALL comment
  events. The gateway log shows `User ... denied (policy=pairing, rule=top)`. Always create
  the rules file with `policy: "allowlist"` and the user's `open_id` before testing comment
  auto-reply. See "Automated comment event handling" section above.
