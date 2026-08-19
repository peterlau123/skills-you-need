#!/usr/bin/env python3
"""pdf-inspector 提取脚本 — PDF → 智能分类 + 结构化 Markdown。

用法:
    python extract_pdf_inspector.py document.pdf                # 分类 + Markdown 输出到 stdout
    python extract_pdf_inspector.py document.pdf -o out.md      # 保存到文件
    python extract_pdf_inspector.py document.pdf --pages        # 逐页提取 + OCR 路由标记
    python extract_pdf_inspector.py document.pdf --ocr          # 选择性 OCR（需要外部 OCR 运行时）
    python extract_pdf_inspector.py papers/ -o outdir/          # 批量处理目录
    python extract_pdf_inspector.py document.pdf --json         # JSON 输出（分类+页级信息）

依赖: pip install pdf-inspector
"""
import argparse
import json
import os
import sys


def process_single(path: str, args) -> None:
    import pdf_inspector

    if args.pages:
        result = pdf_inspector.extract_pages_markdown(path)
        print(f"# {os.path.basename(path)} — 共 {len(result.pages)} 页")
        for p in result.pages:
            ocr_flag = " [需要OCR]" if p.needs_ocr else ""
            print(f"\n## Page {p.page}{ocr_flag}\n")
            print(p.markdown or "(无文本)")
        return

    if args.ocr:
        result = pdf_inspector.process_pdf_with_ocr(path)
        print(f"类型: {result.pdf_type}")
        print(f"OCR 路由页数: {result.pages_routed_to_ocr}")
        if result.markdown:
            print(result.markdown)
        return

    result = pdf_inspector.process_pdf(path)

    if args.json:
        pages = pdf_inspector.extract_pages_markdown(path)
        out = {
            "file": path,
            "pdf_type": result.pdf_type,
            "markdown_chars": len(result.markdown or ""),
            "pages_needing_ocr": list(pages.pages_needing_ocr),
            "pages_with_tables": list(pages.pages_with_tables),
            "pages_with_columns": list(pages.pages_with_columns),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    header = f"# {os.path.basename(path)}\n\n> PDF 类型: {result.pdf_type}\n\n---\n\n"
    content = result.markdown or "(无法提取文本，可能是扫描版，试试 --ocr)"
    output = header + content

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"✅ 已保存到 {args.output}（类型: {result.pdf_type}, {len(content)} 字符）")
    else:
        print(output)


def process_dir(dirpath: str, args) -> None:
    import pdf_inspector

    outdir = args.output or "extracted/"
    os.makedirs(outdir, exist_ok=True)
    summary = []
    for fname in sorted(os.listdir(dirpath)):
        if not fname.lower().endswith(".pdf"):
            continue
        path = os.path.join(dirpath, fname)
        try:
            result = pdf_inspector.process_pdf(path)
            md = result.markdown or ""
            outfile = os.path.join(outdir, fname[:-4] + ".md")
            with open(outfile, "w", encoding="utf-8") as f:
                f.write(md)
            summary.append(f"{fname}: {result.pdf_type}, {len(md)} 字符 -> {outfile}")
            print(f"✅ {fname}: {result.pdf_type} ({len(md)} 字符)")
        except Exception as e:
            summary.append(f"{fname}: 失败 ({e})")
            print(f"❌ {fname}: {e}")

    print(f"\n完成: {len(summary)} 个 PDF，输出目录 {outdir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="pdf-inspector 提取工具")
    parser.add_argument("input", help="PDF 文件或目录")
    parser.add_argument("-o", "--output", help="输出文件（单文件）或输出目录（批量）")
    parser.add_argument("--pages", action="store_true", help="逐页提取并标记 OCR 需求")
    parser.add_argument("--ocr", action="store_true", help="选择性 OCR（需要 OCR 运行时）")
    parser.add_argument("--json", action="store_true", help="JSON 摘要输出")
    args = parser.parse_args()

    if os.path.isdir(args.input):
        process_dir(args.input, args)
    else:
        process_single(args.input, args)


if __name__ == "__main__":
    main()
