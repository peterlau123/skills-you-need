# Wiki Node Management & Batch Block Writing

Verified 2026-08-14 on app `cli_aa951cb0dfb9dbda` (chat-bot, ai-engineer profile).

## Wiki node resolution (two-step)

Wiki URLs use node tokens, not document tokens. Always resolve first:

```
GET /open-apis/wiki/v2/spaces/get_node?token=<url-token>
→ data.node.obj_token     # the actual doc_id (for docx) or file_token (for files)
  data.node.obj_type      # "docx" | "file" | "sheet" | "bitable" | ...
  data.node.space_id      # wiki space ID (needed for child node creation)
  data.node.parent_node_token  # parent node (for navigation)
  data.node.title         # node title
```

## Wiki child node creation APIs

### Create child node directly (requires wiki space edit permission)

```
POST /open-apis/wiki/v2/spaces/{space_id}/nodes
Body: {
  "obj_type": "docx",
  "parent_node_token": "<parent_node_token>",
  "node_type": "origin",
  "title": "子文档标题"
}
→ data.node.node_token, data.node.obj_token
```

**Permissions needed**: `wiki:wiki` or `wiki:node:create` scope + wiki space membership with
edit/admin role. The chat-bot app (`cli_aa95…`) does NOT have this — returns:
```json
{"code": 131006, "msg": "permission denied: node permission denied, tenant needs edit permission."}
```

The janus app (`cli_aae7…`) has `wiki:wiki:readonly` only — returns:
```json
{"code": 99991672, "msg": "Access denied. One of the following scopes is required: [wiki:wiki, wiki:node:create]"}
```

### Move standalone doc into wiki (also requires wiki edit permission)

```
POST /open-apis/wiki/v2/spaces/{space_id}/nodes/move_docs_to_wiki
Body: {
  "parent_wiki_token": "<parent_node_token>",
  "obj_type": "docx",
  "obj_token": "<doc_id>"
}
```

Returns `131006 "permission denied: no destination parent node permission"` if the bot is not
a wiki space member with edit permission.

### List wiki space members (works with read access)

```
GET /open-apis/wiki/v2/spaces/{space_id}/members?page_size=20
→ data.members[]: {member_id, member_type ("openid"|"department"|"openchat"), member_role ("admin"|"member"), member_perm ("admin"|"view")}
```

### Get bot's own open_id

```
GET /open-apis/bot/v3/info
→ data.bot.open_id  (e.g. "ou_2c5661aa4e940b16aee76427d00d9d0c")
```

Check if this open_id appears in the wiki space members list. If missing or `member_perm: "view"`,
wiki child node creation is impossible without user action.

## Document permission management APIs (for bot-created docs)

When the bot creates a standalone docx, it is the owner. These APIs let the bot grant
access to the user or transfer ownership.

### Add user as collaborator

```
POST /open-apis/drive/v1/permissions/{doc_token}/members?type=docx
Body: {"member_type":"openid","member_id":"<user_open_id>","perm":"full_access"}
```

- `perm` values: `view`, `edit`, `full_access`.
- Only works when the bot is the document owner. Returns `1063002 "Permission denied"` otherwise.
- Verified 2026-08-14: successfully added user with `full_access` on a bot-created doc.

### Transfer ownership (verified 2026-08-14)

```
POST /open-apis/drive/v1/permissions/{doc_token}/members/transfer_owner?type=docx
Body: {"member_type":"openid","member_id":"<user_open_id>"}
→ {"code":0,"data":{},"msg":"Success"}
```

- Makes the user the document owner. The bot retains collaborator access.
- After transfer, the user can move/delete/reshare the doc from the Feishu UI.
- Use this when the bot can't move docs into wiki (lacks wiki space edit permission) —
  transfer ownership so the user can move it manually.

### List current collaborators

```
GET /open-apis/drive/v1/permissions/{doc_token}/members?type=docx
→ data.items[]: {member_id, member_type, perm, perm_type}
```

- Use to verify that a collaborator was added successfully or check existing permissions.

## Fallback workflow (when bot lacks wiki edit permission)

1. Create standalone docx: `POST /docx/v1/documents` with `{"folder_token": ""}`
2. Write blocks into the doc (see batch writing below)
3. Add user as collaborator (full_access): `POST /drive/v1/permissions/{doc_id}/members?type=docx`
4. Transfer ownership to user: `POST /drive/v1/permissions/{doc_id}/members/transfer_owner?type=docx`
5. User moves the doc into wiki via Feishu UI: open doc → "···" → 移动 → select wiki page
   - Step 3 alone gives the user access but NOT the ability to move the doc.
   - Step 4 (ownership transfer) is required for the user to move it into wiki.

## Batch block writing (for large documents)

### API limit

The `POST /docx/v1/documents/{doc_id}/blocks/{doc_id}/children` endpoint accepts a maximum of
**50 blocks per request**. Exceeding this returns an error.

### Batch writing pattern

For large documents (100+ blocks), use a Python script with `urllib.request`:

```python
import json, time, urllib.request

def write_blocks(token, doc_id, blocks, batch_size=45):
    for i in range(0, len(blocks), batch_size):
        batch = blocks[i:i+batch_size]
        body = json.dumps({"children": batch}).encode()
        url = f"https://open.feishu.cn/open-apis/docx/v1/documents/{doc_id}/blocks/{doc_id}/children"
        req = urllib.request.Request(url, data=body,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            method="POST")
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            if result.get("code") != 0:
                print(f"ERROR batch {i//batch_size}: {json.dumps(result, ensure_ascii=False)[:500]}")
                return False
        print(f"  Batch {i//batch_size + 1}: OK ({len(batch)} blocks)")
        time.sleep(0.5)  # rate limit courtesy
    return True
```

### Verified scale

- 375 blocks written in 9 batches of 45 on 2026-08-14 — no errors, ~0.5s per batch.
- Document was 17,367 characters of content covering vLLM architecture analysis.

### Block construction helpers

```python
def text_run(content, bold=False, code=False):
    style = {}
    if bold: style["bold"] = True
    if code: style["inline_code"] = True
    return {"text_run": {"content": content, "text_element_style": style} if style else {"content": content}}

def h1(text): return {"block_type": 3, "heading1": {"elements": [text_run(text)]}}
def h2(text): return {"block_type": 4, "heading2": {"elements": [text_run(text)]}}
def h3(text): return {"block_type": 5, "heading3": {"elements": [text_run(text)]}}
def para(*elements): return {"block_type": 2, "text": {"elements": list(elements)}}
def bullet(text): return {"block_type": 12, "bullet": {"elements": [text_run(text)]}}
def ordered(text): return {"block_type": 13, "ordered": {"elements": [text_run(text)]}}
def code_block(text): return {"block_type": 14, "code": {"elements": [text_run(text)]}}
def divider(): return {"block_type": 22, "divider": {}}  # "divider": {} is REQUIRED — bare {"block_type": 22} causes code 1770001 "invalid param" that rejects the ENTIRE batch
```

## Additional block types (beyond what's in the main SKILL.md)

| block_type | Type | Content field |
|---|---|---|
| 6-11 | Heading 4-9 | `headingN.elements[].text_run.content` |
| 14 | Code block | `code.elements[].text_run.content` |
| 15 | Quote | `quote.elements[].text_run.content` |
| 22 | Divider | (no content) |
| 31 | Callout | `callout.elements[].text_run.content` |
