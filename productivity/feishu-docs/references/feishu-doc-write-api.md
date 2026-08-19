# Feishu Doc Write API — create + block content

Verified 2026-08-06 on app `cli_aae754581ab89bd1` (janus-model-adapt profile).

## Prerequisites

1. App scopes enabled in Feishu console:
   - `docx:document` (or `docx:document:create`) — create + write blocks
2. App version published (version management → 创建版本 → 发布). Enabling scope alone does NOT
   take effect until published — API returns `code: 99991672` with the grant link.

## Flow

### Step 1: Get tenant_access_token (same as read flow)

```bash
TOKEN=$(curl -s -X POST "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal" \
  -H "Content-Type: application/json" \
  -d '{"app_id":"...","app_secret":"..."}' \
  | python3 -c "import json,sys; print(json.load(sys.stdin)['tenant_access_token'])")
```

### Step 2: Create a new document

```bash
CREATE=$(curl -s -X POST "https://open.feishu.cn/open-apis/docx/v1/documents" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"folder_token":""}')

DOC_ID=$(echo "$CREATE" | python3 -c "import json,sys; print(json.load(sys.stdin)['data']['document']['document_id'])")
```

- `folder_token: ""` → creates in the app's default cloud space folder
- Response: `data.document.{document_id, revision_id, title}`
- Document URL: `https://<tenant>.feishu.cn/docx/<document_id>`

### Step 3: Write blocks (children of the document root)

The document root block ID = the document ID. Write top-level blocks as children of it:

```bash
curl -s -X POST "https://open.feishu.cn/open-apis/docx/v1/documents/$DOC_ID/blocks/$DOC_ID/children" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "children": [
      {
        "block_type": 3,
        "heading1": {
          "elements": [{"text_run": {"content": "周报标题"}}]
        }
      },
      {
        "block_type": 2,
        "text": {
          "elements": [{"text_run": {"content": "段落正文内容..."}}]
        }
      }
    ]
  }'
```

### Block type reference

| block_type | Type | Content field path |
|---|---|---|
| 1 | Page (document root) | — |
| 2 | Text / paragraph | `text.elements[].text_run.content` |
| 3 | Heading 1 | `heading1.elements[].text_run.content` |
| 4 | Heading 2 | `heading2.elements[].text_run.content` |
| 5 | Heading 3 | `heading3.elements[].text_run.content` |
| 6 | Heading 4 | `heading4.elements[].text_run.content` |
| 7 | Heading 5 | `heading5.elements[].text_run.content` |
| 8 | Heading 6 | `heading6.elements[].text_run.content` |
| 9 | Heading 7 | `heading7.elements[].text_run.content` |
| 10 | Heading 8 | `heading8.elements[].text_run.content` |
| 11 | Heading 9 | `heading9.elements[].text_run.content` |
| 12 | Bullet list | `bullet.elements[].text_run.content` |
| 13 | Ordered list | `ordered.elements[].text_run.content` |
| 14 | Code block | `code.elements[].text_run.content` |
| 15 | Quote | `quote.elements[].text_run.content` |
| 22 | Divider | (no content) |
| 27 | Table | `table.property.{row_size, col_size}` (needs separate cell write API) |
| 31 | Callout | `callout.elements[].text_run.content` |

### Text run formatting

`text_run` supports `text_element_style` for inline formatting:

```json
{
  "text_run": {
    "content": "加粗文字",
    "text_element_style": {
      "bold": true,
      "italic": false,
      "strikethrough": false,
      "underline": false,
      "inline_code": false,
      "background_color": 1
    }
  }
}
```

### Error codes

| code | Meaning | Fix |
|---|---|---|
| 0 | Success | — |
| 99991672 | Scope not granted | Enable scope in console + publish new app version |
| 1061002 | Params error | Check body fields are JSON, not query params |
| 1254040 | Document not found | Check document_id is correct |
| 1254003 | No edit permission | Add app as 可编辑 collaborator on the document |
