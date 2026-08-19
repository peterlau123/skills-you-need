# Feishu docx: splicing content into an EXISTING document (descendant endpoint)

Verified 2026-08-17 on the chat-bot app (`cli_aa95…`) against a large wiki doc
("vLLM 技术架构分析", ~300 blocks). All endpoints under
`https://open.feishu.cn/open-apis/docx/v1`.

## The two create endpoints and when to use each

| Endpoint | Body shape | Use for |
|---|---|---|
| `POST /documents/<doc_id>/blocks/<doc_id>/children` | `{"children": [flat block objects], "index": N}` | Simple flat blocks (text, headings, bullets, code). Table **without** content only. |
| `POST /documents/<doc_id>/blocks/<doc_id>/descendant` | `{"index": N, "children_id": ["tmp1",...], "descendants": [...]}` | **Nested/hierarchical content — tables with cell text, any block with children.** This is the ONLY way to create a table that already contains text. |

- `children` endpoint with a `table` block: `table.cells` must be `string[]` of
  cell-block IDs, and cell blocks cannot be created in the same flat call →
  any attempt to inline cells as block objects fails with `code: 9499
  "Invalid parameter type in json: cells"`. **Do not fight this — use descendant.**
- `descendant` requires BOTH `children_id` (temp IDs of the TOP-LEVEL blocks
  only, e.g. `["tbl_1", "ov_code"]`) and `descendants` (every block in the
  tree, each with a `block_id` matching a temp ID, a `children` array of the
  temp IDs of ITS children, and `children: []` on leaves). Response maps temp
  IDs → real IDs in `block_id_relations`.
- `index` = insertion position among the page block's children (0-based).
  To splice before a known heading: GET the page's children, find the heading
  block's index, pass that index. Verified: inserting at `index=121` and
  `index=123` into a 300-block doc both worked.

## Block types that matter for nested writes (descendant numbering)

| block_type | Meaning | Content field |
|---|---|---|
| 2 | Text | `text.elements[].text_run.content` |
| 3 / 4 / 5 | H1 / H2 / H3 | `heading1|2|3.elements[].text_run.content` |
| 14 | Code block | `code.elements[].text_run.content` + `code.style.language` |
| 31 | **Table** | `table.property.{row_size, column_size, column_width, header_row}` |
| 32 | **Table cell** | `table_cell: {}` (empty obj) + `children: ["<text tmp id>"]` |

Table structure (8 rows × 2 cols, header row):
```json
{
  "block_id": "tbl_1", "block_type": 31,
  "table": {"property": {"row_size": 8, "column_size": 2,
             "column_width": [220, 480], "header_row": true}},
  "children": ["cell_0_0", "cell_0_1", "cell_1_0", "..."]   // ROW-MAJOR, one tmp id per cell
},
{
  "block_id": "cell_0_0", "block_type": 32, "table_cell": {},
  "children": ["cell_0_0_text"]
},
{
  "block_id": "cell_0_0_text", "block_type": 2,
  "text": {"elements": [{"text_run": {"content": "cell content"}}]},
  "children": []
}
```
Rules: cell count must equal row_size × column_size; every cell needs ≥1 child
block (an empty cell still needs an empty text block); `table_cell` content
field must be present (empty `{}`).

## Code block language enum (verified values)

`code.style.language`: 1=PlainText, 39=Markdown, 49=Python, 53=Rust, 67=YAML…
**There is NO mermaid option.** Feishu `diagram` blocks only support 流程图 (1)
and UML (2) — they cannot render arbitrary mermaid. To deliver a mermaid
diagram into a Feishu doc: put the mermaid source in a code block with
`language: 1` (PlainText) and tell the user to copy it into their mermaid
editor (or offer to convert to a Feishu diagram block manually). `block_type:
35` / `style.language: 11` (used in older docs) is WRONG — 35 is not a code
block in current API docs and returns `1770001 invalid param`.

## PATCH batch_update validation (update_text gotcha)

`PATCH /documents/<doc_id>/blocks/batch_update` with `update_text` fails
`code: 99992402 field validation failed` unless BOTH extra fields are present:
```json
{
  "requests": [{
    "block_id": "doxcn...",
    "update_text": {
      "elements": [{"text_run": {"content": "new text"}}],
      "style": {"align": 1},
      "fields": [1]
    }
  }]
}
```
- `style.align`: 1=left, 2=center, 3=right (required)
- `fields`: which style fields to apply, e.g. `[1]` for align (required)
- Missing `style` → error names `update_text.style`; missing `fields` → error
  names `update_text.fields`. Both must be supplied even for a plain text swap.
- This is the reliable way to REPURPOSE an existing block (see next section).

## Deleting blocks: plain DELETE 404s; use repurpose or batch_delete

`DELETE /documents/<doc_id>/blocks/<block_id>` returns `404 page not found`
(on this app/tenant, 2026-08-17 — even with `?document_revision_id=-1`).
The API docs list "删除块" but the endpoint path did not resolve.

Two working alternatives:
1. **Repurpose instead of delete** (verified): if you created throwaway test
   blocks (e.g. while probing the API), PATCH them via `batch_update` +
   `update_text` into the real content, then insert the rest around them with
   `descendant`. No delete needed, no gaps.
2. **batch_delete endpoint** (verified in an earlier session): 
   `DELETE /documents/<doc_id>/blocks/<doc_id>/children/batch_delete`
   body `{"start_index": 0, "end_index": N}` — deletes by index range.

## Worked pattern: splice a new section before an existing heading

1. GET `blocks/<doc_id>/children?page_size=500`, walk the items, find the
   heading block whose text you want to insert before → record its `index`.
2. Build the descendant payload with that index.
3. Verify: GET `raw_content` and assert your new strings appear; assert the
   original headings still exist (raw_content has no structure info, so check
   a couple of untouched strings too).

## Rate limits

创建块/嵌套块/删除块/更新块 share a per-document concurrency limit of 3/s
(HTTP 429 on exceed). Keep a small sleep between sequential write calls.
