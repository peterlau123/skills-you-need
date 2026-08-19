# Feishu Open API Reference (mx001, ai-engineer profile)

Condensed reference for the Feishu/Lark Open API endpoints used by the feishu-docs skill.
All endpoints require `Authorization: Bearer <tenant_access_token>`.

## 1. Auth: tenant_access_token

```
POST /open-apis/auth/v3/tenant_access_token/internal
Content-Type: application/json
Body: {"app_id": "...", "app_secret": "..."}
→ { "code": 0, "tenant_access_token": "t-xxx", "expire": 7200 }
```

- Token is valid for 2 hours. Cache it within a session.
- Both apps use this same endpoint; only `app_id` / `app_secret` differ.

## 2. Wiki node resolution (two-step)

Wiki URL tokens are **node tokens**, not document/file tokens. Resolve first:

```
GET /open-apis/wiki/v2/spaces/get_node?token=<url_token>
→ data.node.obj_token, data.node.obj_type, data.node.space_id
```

### obj_type values and what to do

| obj_type | Meaning | Read method |
|---|---|---|
| `docx` | Native Feishu doc | `GET /open-apis/docx/v1/documents/<obj_token>/raw_content` |
| `file` | File attachment (.docx, .pptx, .pdf, etc.) | `GET /open-apis/drive/v1/files/<obj_token>/download` (binary) |
| `sheet` | Spreadsheet | Sheets API |
| `bitable` | Base / multidimensional table | Bitable API |
| `mindnote` | Mind map | MindNote API |

**Key gotcha**: `obj_type: file` means the docx `raw_content` API returns `404 / 1770002`.
Use the drive download endpoint instead.

## 3. Docx read

```
GET /open-apis/docx/v1/documents/<doc_token>/raw_content
→ data.content (plain text string)
```

- Works only for native Feishu docx documents (obj_type=docx).
- Returns `404 / 1770002 "not found"` if the token is a file token, not a docx token.

## 4. Drive file download

```
GET /open-apis/drive/v1/files/<file_token>/download
→ binary content (HTTP 200)
```

### Download error diagnostics

| HTTP | code | cause | fix |
|---|---|---|---|
| 400 | 99991672 | App lacks `drive:file:download` scope (or scope not published) | Console → 权限管理 → add scope → 版本管理 → 创建版本 → 发布 |
| 403 | (empty body) | App has scope but is NOT a file collaborator | User shares file with bot in Feishu UI (分享 → add bot) |
| 403 | 1063004 | App tried to self-grant collaborator access | Only file owner can share; ask user |
| 404 | 1770002 | Token is wrong type (e.g. using docx API on a file token) | Use drive download endpoint instead |

- `GET /open-apis/drive/v1/medias/<file_token>/download` — alternative endpoint, same errors.
  Do NOT use as workaround for permission issues.
- `GET /open-apis/drive/v1/files/<file_token>` (meta) — often returns non-JSON (rate-limit page);
  do not rely on it. The download endpoint is the reliable path.

### Adding a collaborator (rarely works via API)

```
POST /open-apis/drive/v1/permissions/<file_token>/members?type=file
Body: {"member_type": "openchat", "member_id": "...", "perm": "full_access"}
```

- Requires `drive:drive` scope on the calling app AND the caller must already have share
  permission on the file. In practice, self-granting fails with `1063002 "Permission denied"`.
  Ask the user to share the file manually instead.

## 5. Drive file upload

```
POST /open-apis/drive/v1/files/upload_all  (multipart, <20MB)
```

Gotcha: EVERY field (`file_name`, `parent_type`, `size`, `parent_node`) must be multipart
form-data in the body — query params return `code: 1061002`.

Response: `data.file_token` → link as `https://<tenant>.feishu.cn/file/<file_token>`.

## 6. Docx write (create + blocks)

### Create document

```
POST /open-apis/docx/v1/documents
Body: {"folder_token": ""}   # empty = app default folder
→ data.document.document_id
```

### Write blocks

```
POST /open-apis/docx/v1/documents/<doc_id>/blocks/<doc_id>/children
```

The document root IS a block — use `doc_id` as both document ID and parent block ID.

### Block types

| block_type | Type | Content field |
|---|---|---|
| 2 | Text/paragraph | `text.elements[].text_run.content` |
| 3 | Heading 1 | `heading1.elements[].text_run.content` |
| 4 | Heading 2 | `heading2.elements[].text_run.content` |
| 5 | Heading 3 | `heading3.elements[].text_run.content` |
| 12 | Bullet list | `bullet.elements[].text_run.content` |
| 13 | Ordered list | `ordered.elements[].text_run.content` |
| 27 | Table | `table.property.row_size`, `col_size` + separate cells API |

### Write gotchas

- Dev-mode apps: scope must be enabled AND a new version published (版本管理 → 创建版本 → 发布).
  Until published, API returns `99991672` even with the scope checked.
- Writing to existing wiki docs requires the app to be a collaborator with 可编辑 permission.

## 7. IM message read

```
GET /open-apis/im/v1/messages/<message_id>
→ msg_type, data.items[0].body.content (JSON), data.items[0].body.content_v2 (markdown array)
```

- Use the chat-bot app (cli_aa95…); the janus app is not a DM member (fails `230002`).
- In DMs, the session-key `:om_...` suffix IS the message_id of the replied-to message.

## App credentials summary (do not echo secrets)

| App | app_id | Creds location | Key scopes |
|---|---|---|---|
| janus (read) | cli_aae7… | `~/.hermes/profiles/janus-model-adapt/secrets/feishu_app.json` | `docx:document:readonly`, `wiki:wiki:readonly`, `drive:drive:readonly` |
| chat-bot (read+write) | cli_aa95… | profile `.env` (`FEISHU_APP_ID` / `FEISHU_APP_SECRET`) | `docx:document`, `docx:document:create`, `drive:file:upload` |

- Two-app split: read with janus, write with chat-bot.
- If one app fails with `99991672`, try the other before asking the user.
- Never write `app_secret` to memory or echo it in chat.
