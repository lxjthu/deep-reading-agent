"""Shared HTML rendering for protected Markdown previews."""
from __future__ import annotations

from html import escape

import markdown


def render_markdown_preview_html(content: str, filename: str) -> str:
    html_content = markdown.markdown(content, extensions=["tables", "fenced_code", "toc"])
    safe_filename = escape(filename)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{safe_filename}</title>
    <style>
        :root {{
            color-scheme: light;
            --page-bg: #f6f7f5;
            --paper: #ffffff;
            --ink: #1f2933;
            --muted: #667085;
            --line: #e4e7ec;
            --soft: #f2f7f4;
            --accent: #047857;
            --accent-strong: #065f46;
        }}
        * {{ box-sizing: border-box; }}
        body {{
            margin: 0;
            background: var(--page-bg);
            color: var(--ink);
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Noto Sans SC', Roboto, sans-serif;
            line-height: 1.78;
        }}
        .preview-shell {{
            max-width: 1040px;
            margin: 0 auto;
            padding: 32px 18px 56px;
        }}
        .preview-header {{
            margin-bottom: 18px;
            border: 1px solid var(--line);
            background: var(--paper);
            padding: 22px 26px;
            box-shadow: 0 12px 30px rgba(16, 24, 40, 0.06);
        }}
        .preview-kicker {{
            margin: 0 0 8px;
            color: var(--accent);
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }}
        .preview-title {{
            margin: 0;
            color: #101828;
            font-size: clamp(24px, 4vw, 38px);
            line-height: 1.2;
            overflow-wrap: anywhere;
        }}
        article {{
            border: 1px solid var(--line);
            background: var(--paper);
            padding: 34px 38px;
            box-shadow: 0 18px 45px rgba(16, 24, 40, 0.08);
        }}
        article > :first-child {{ margin-top: 0; }}
        article > :last-child {{ margin-bottom: 0; }}
        h1, h2, h3, h4 {{
            color: #111827;
            line-height: 1.35;
            scroll-margin-top: 24px;
        }}
        h1 {{
            margin: 0 0 24px;
            padding-bottom: 12px;
            border-bottom: 2px solid #d1e7dd;
            font-size: 30px;
        }}
        h2 {{
            margin: 34px 0 14px;
            padding-left: 12px;
            border-left: 4px solid var(--accent);
            font-size: 22px;
        }}
        h3 {{ margin: 26px 0 10px; font-size: 18px; }}
        h4 {{ margin: 22px 0 8px; font-size: 16px; }}
        p {{ margin: 0 0 14px; }}
        a {{ color: #0369a1; text-decoration-thickness: 1px; text-underline-offset: 3px; }}
        ul, ol {{ padding-left: 1.45rem; }}
        li {{ margin: 5px 0; }}
        blockquote {{
            margin: 18px 0;
            border-left: 4px solid var(--accent);
            background: var(--soft);
            padding: 12px 16px;
            color: #344054;
        }}
        code {{
            border-radius: 5px;
            background: #eef2f6;
            padding: 2px 6px;
            font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
            font-size: 0.92em;
        }}
        pre {{
            overflow-x: auto;
            border: 1px solid #d0d5dd;
            border-radius: 8px;
            background: #111827;
            padding: 16px;
        }}
        pre code {{ background: transparent; color: #f9fafb; padding: 0; }}
        table {{
            display: block;
            width: 100%;
            overflow-x: auto;
            border-collapse: collapse;
            margin: 18px 0;
            font-size: 14px;
        }}
        th, td {{ border: 1px solid var(--line); padding: 9px 11px; vertical-align: top; }}
        th {{ background: #f2f4f7; color: #344054; font-weight: 700; }}
        tr:nth-child(even) td {{ background: #fcfcfd; }}
        hr {{ border: 0; border-top: 1px solid var(--line); margin: 30px 0; }}
        img {{ max-width: 100%; height: auto; }}
        .MathJax {{ overflow-x: auto; overflow-y: hidden; max-width: 100%; }}
        @media (max-width: 720px) {{
            .preview-shell {{ padding: 14px 10px 32px; }}
            .preview-header {{ padding: 18px; }}
            article {{ padding: 22px 18px; }}
            h1 {{ font-size: 24px; }}
            h2 {{ font-size: 19px; }}
        }}
        @media print {{
            body {{ background: #fff; }}
            .preview-shell {{ max-width: none; padding: 0; }}
            .preview-header, article {{ border: 0; box-shadow: none; }}
        }}
    </style>
    <script>
        window.MathJax = {{
            tex: {{
                inlineMath: [['$', '$'], ['\\(', '\\)']],
                displayMath: [['$$', '$$'], ['\\[', '\\]']],
                processEscapes: true
            }},
            options: {{
                skipHtmlTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code']
            }}
        }};
    </script>
    <script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script>
</head>
<body>
    <main class="preview-shell">
        <header class="preview-header">
            <p class="preview-kicker">Markdown Preview</p>
            <h1 class="preview-title">{safe_filename}</h1>
        </header>
        <article>
            {html_content}
        </article>
    </main>
</body>
</html>"""
