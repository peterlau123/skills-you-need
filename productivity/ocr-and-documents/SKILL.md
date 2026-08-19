---
name: ocr-and-documents
description: "Extract text from PDFs/scans (pdf-inspector, pymupdf, marker-pdf)."
version: 2.4.0
author: Hermes Agent
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [PDF, Documents, Research, Arxiv, Text-Extraction, OCR]
    related_skills: [pdf, docx, powerpoint]
---

# PDF & Document Extraction

For DOCX: see the `docx` skill (create/edit) or use `python-docx` for structured reads.
For PPTX: see the `powerpoint` skill (full create/read/edit support).
For PDF manipulation (merge, split, forms, watermarks, creation): see the `pdf` skill.
This skill covers **text extraction from PDFs and scanned documents**.

## Step 1: Remote URL Available?

If the document has a URL, **always try `web_extract` first**:

```
web_extract(urls=["https://arxiv.org/pdf/2402.03300"])
web_extract(urls=["https://example.com/report.pdf"])
```

This handles PDF-to-markdown conversion via Firecrawl with no local dependencies.

Only use local extraction when: the file is local, web_extract fails, or you need batch processing.

## Step 2: Choose Local Extractor

| Feature | **pdf-inspector (~5MB)** | pymupdf (~25MB) | marker-pdf (~3-5GB) |
|---------|--------------------------|-----------------|---------------------|
| **Text-based PDF** | ✅ **首选（0.1-0.3s）** | ✅ | ✅ |
| **Scanned PDF (OCR)** | ✅ 选择性 OCR（PP-OCRv6） | ❌ | ✅ (90+ 语言) |
| **智能分类** | ✅ TextBased/Scanned/Image/Mixed + 置信度 | ❌ | ❌ |
| **Markdown 输出** | ✅ 原生（标题/表格/代码块/列表） | ✅ (pymupdf4llm，质量较低) | ✅ (高质量) |
| **Tables** | ✅ (0.814 TEDS) | ✅ (basic) | ✅ (high accuracy) |
| **Reading order** | ✅ 多栏自动检测 | ❌ | ✅ |
| **Equations / LaTeX** | ❌ | ❌ | ✅ |
| **OCR 路由** | ✅ 只对 needs_ocr 页运行 | ❌ | ❌ |
| **Install size** | ~5MB | ~25MB | ~3-5GB (PyTorch + models) |
| **Speed** | **0.1-0.5s/文档** | Instant | ~1-14s/page (CPU) |

**Decision**:
- **文本型 PDF（论文/报告/财务文档）→ pdf-inspector 首选**：最快 + 结构化 Markdown + 自动分类
- 需要 OCR 的扫描件 → pdf-inspector 先试（`process_pdf_with_ocr` 选择性 OCR）；效果不够再 marker-pdf
- 需要方程/LaTeX/表单 → marker-pdf

> pdf-inspector 已安装于 Hermes venv（`/home/ecs-user/.hermes/hermes-agent/venv/`，v1.15.0，uv 安装）。
> 基准（opendataloader-bench 200 篇）：综合 0.875 超 pymupdf4llm 0.735 / markitdown 0.589，200 篇 0.47s。

---

## pdf-inspector (首选, ~5MB, Rust)

```bash
uv pip install --python /path/to/venv/bin/python pdf-inspector
```

**核心 API**（Python）：

```python
import pdf_inspector

# 智能分类 + 全文 Markdown（一次调用）
result = pdf_inspector.process_pdf("document.pdf")
print(result.pdf_type)     # "text_based" / "scanned" / "image_based" / "mixed"
print(result.markdown)     # 结构化 Markdown（标题/表格/代码块已识别）

# 逐页提取 + OCR 路由标记
pages = pdf_inspector.extract_pages_markdown("document.pdf")
for p in pages.pages:      # PageMarkdown(page, markdown, needs_ocr)
    if p.needs_ocr:
        print(f"Page {p.page} 需要 OCR")

# 选择性 OCR（只处理需要 OCR 的页）
ocr = pdf_inspector.process_pdf_with_ocr("document.pdf")
print(ocr.pages_routed_to_ocr)

# 其他 API
pdf_inspector.classify_pdf("document.pdf")          # 仅分类（10-50ms 采样）
pdf_inspector.extract_text("document.pdf")          # 纯文本
pdf_inspector.extract_text_with_positions("document.pdf")  # 位置感知文本
pdf_inspector.extract_structure_elements("document.pdf")   # 结构元素
```

**批量处理**：

```python
import pdf_inspector, os, json

for f in os.listdir("papers/"):
    if f.endswith(".pdf"):
        r = pdf_inspector.process_pdf(os.path.join("papers", f))
        if r.pdf_type == "text_based":
            with open(f"{f[:-4]}.md", "w") as out:
                out.write(r.markdown)
        else:
            print(f"{f} 是 {r.pdf_type}，需要 OCR")
```

**写笔记工作流**（论文 PDF → Markdown → 笔记素材）：
1. `process_pdf()` 拿到结构化 Markdown
2. 用 Markdown 的标题层级/表格作为笔记结构骨架
3. 扫描页（`needs_ocr=True`）标记出来，视需要补 OCR 或从摘要补全

---

## pymupdf (lightweight)

```bash
pip install pymupdf pymupdf4llm
```

**Via helper script**:
```bash
python scripts/extract_pymupdf.py document.pdf              # Plain text
python scripts/extract_pymupdf.py document.pdf --markdown    # Markdown
python scripts/extract_pymupdf.py document.pdf --tables      # Tables
python scripts/extract_pymupdf.py document.pdf --images out/ # Extract images
python scripts/extract_pymupdf.py document.pdf --metadata    # Title, author, pages
python scripts/extract_pymupdf.py document.pdf --pages 0-4   # Specific pages
```

**Inline**:
```bash
python3 -c "
import pymupdf
doc = pymupdf.open('document.pdf')
for page in doc:
    print(page.get_text())
"
```

---

## marker-pdf (high-quality OCR)

```bash
# Check disk space first
python scripts/extract_marker.py --check

pip install marker-pdf
```

**Via helper script**:
```bash
python scripts/extract_marker.py document.pdf                # Markdown
python scripts/extract_marker.py document.pdf --json         # JSON with metadata
python scripts/extract_marker.py document.pdf --output_dir out/  # Save images
python scripts/extract_marker.py scanned.pdf                 # Scanned PDF (OCR)
python scripts/extract_marker.py document.pdf --use_llm      # LLM-boosted accuracy
```

**CLI** (installed with marker-pdf):
```bash
marker_single document.pdf --output_dir ./output
marker /path/to/folder --workers 4    # Batch
```

---

## Arxiv Papers

```
# Abstract only (fast)
web_extract(urls=["https://arxiv.org/abs/2402.03300"])

# Full paper
web_extract(urls=["https://arxiv.org/pdf/2402.03300"])

# Search
web_search(query="arxiv GRPO reinforcement learning 2026")
```

## Split, Merge & Search

pymupdf handles these natively — use `execute_code` or inline Python:

```python
# Split: extract pages 1-5 to a new PDF
import pymupdf
doc = pymupdf.open("report.pdf")
new = pymupdf.open()
for i in range(5):
    new.insert_pdf(doc, from_page=i, to_page=i)
new.save("pages_1-5.pdf")
```

```python
# Merge multiple PDFs
import pymupdf
result = pymupdf.open()
for path in ["a.pdf", "b.pdf", "c.pdf"]:
    result.insert_pdf(pymupdf.open(path))
result.save("merged.pdf")
```

```python
# Search for text across all pages
import pymupdf
doc = pymupdf.open("report.pdf")
for i, page in enumerate(doc):
    results = page.search_for("revenue")
    if results:
        print(f"Page {i+1}: {len(results)} match(es)")
        print(page.get_text("text"))
```

No extra dependencies needed — pymupdf covers split, merge, search, and text extraction in one package.

---

## Notes

- `web_extract` is always first choice for URLs
- pymupdf is the safe default — instant, no models, works everywhere
- marker-pdf is for OCR, scanned docs, equations, complex layouts — install only when needed
- Both helper scripts accept `--help` for full usage
- marker-pdf downloads ~2.5GB of models to `~/.cache/huggingface/` on first use
- For Word docs: `pip install python-docx` (better than OCR — parses actual structure)
- For PowerPoint: see the `powerpoint` skill (uses python-pptx)
