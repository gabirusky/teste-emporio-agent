"""Render submission/technical_case.md into the deliverable PDF.

Pipeline: Markdown -> HTML (Python-Markdown) -> styled HTML -> PDF via WeasyPrint.
Style mirrors the previously shipped PDF: Liberation Sans body, amber title banner,
gray-100 table headers, gray-50 code blocks, gray-200 table borders.
Run:  python submission/render_pdf.py
"""
from __future__ import annotations

import pathlib

import markdown
from weasyprint import HTML

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "submission" / "technical_case.md"
DST = ROOT / "Gabriel Pereira - AI Engineer - Full-Stack para Aplicações com IA Generativa.pdf"

CSS = """
@page {
  size: A4;
  margin: 57pt 57pt 70pt 57pt;
}
body {
  font-family: "Liberation Sans", sans-serif;
  font-size: 9.8pt;
  color: #1f2937;
  line-height: 1.4;
}
h1 {
  font-size: 19pt;
  font-weight: bold;
  color: #b45309;
  margin: 0 0 3pt 0;
  line-height: 1.35;
}
h1 .subtitle {
  font-size: 9pt;
  font-weight: normal;
  color: #4b5563;
  display: block;
  margin-top: 1.5pt;
}
h1 .meta {
  font-size: 8pt;
  color: #6b7280;
  display: block;
  margin-top: 1.5pt;
  line-height: 1.4;
}
h2 {
  font-size: 12pt;
  font-weight: bold;
  color: #b45309;
  margin-top: 13pt;
  margin-bottom: 4pt;
  padding-bottom: 2pt;
  border-bottom: 1.5pt solid #d97706;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 6pt 0;
  font-size: 8.6pt;
}
h2.appendix {
  margin-top: 20pt;
}
h3 {
  font-size: 11.5pt;
  font-weight: bold;
  color: #374151;
  margin-top: 14pt;
  margin-bottom: 6pt;
}
p {
  margin: 0 0 8pt 0;
}
ul, ol {
  margin: 0 0 8pt 0;
  padding-left: 20pt;
}
li {
  margin-bottom: 3pt;
}
code {
  background-color: #f3f4f6;
  font-family: "Liberation Mono", monospace;
  font-size: 9pt;
  padding: 1pt 4pt;
  border-radius: 2pt;
}
pre {
  background-color: #f9fafb;
  border: 1px solid #e5e7eb;
  padding: 8pt;
  font-family: "Liberation Mono", monospace;
  font-size: 9pt;
  margin: 0 0 10pt 0;
  overflow-x: auto;
}
pre code {
  background-color: transparent;
  padding: 0;
  font-size: inherit;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 8pt 0;
  font-size: 9.3pt;
}
th {
  background-color: #f3f4f6;
  border: 1px solid #e5e7eb;
  padding: 4pt 6pt;
  font-weight: bold;
  color: #1f2937;
  text-align: left;
  vertical-align: top;
}
td {
  border: 1px solid #e5e7eb;
  padding: 4pt 6pt;
  vertical-align: top;
}
figure {
  margin: 10pt 0;
  text-align: center;
}
figure img {
  border: 1px solid #d1d5db;
  max-width: 100%;
}
figure.appendix {
  margin-top: 12pt;
  page-break-inside: avoid;
}
figure.appendix img {
  max-width: 44%;
}
figcaption {
  font-size: 8.2pt;
  color: #4b5563;
  margin-top: 3pt;
}
pre {
  background-color: #f9fafb;
  border: 1px solid #e5e7eb;
  padding: 6pt;
  font-family: "Liberation Mono", monospace;
  font-size: 8.2pt;
  margin: 0 0 8pt 0;
  overflow-x: auto;
}
figcaption {
  font-size: 9pt;
  color: #4b5563;
  margin-top: 4pt;
}
"""


def md_to_html(text: str) -> str:
    return markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "sane_lists"],
    )


def build_document(html_body: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>AI Customer Service Agent for Empório da Música — Technical Case Submission</title>
<meta name="author" content="Gabriel Pereira Santos">
<meta name="description" content="Technical case submission for the Artefact AI Engineer role — hybrid LLM agent with function calling, lexical RAG over the store policy PDF, CSV data tools, terminal CLI, and local browser web chat.">
<meta name="keywords" content="AI agent, function calling, RAG, customer service, Python, technical case">
<meta name="generator" content="submission/render_pdf.py (WeasyPrint)">
<style>
{CSS}
</style>
</head>
<body>
{html_body}
</body>
</html>"""


def main() -> None:
    text = SRC.read_text(encoding="utf-8")
    html_body = md_to_html(text)
    document = build_document(html_body)
    HTML(string=document, base_url=str(SRC.parent)).write_pdf(str(DST))
    print(f"Wrote {DST}")


if __name__ == "__main__":
    main()
