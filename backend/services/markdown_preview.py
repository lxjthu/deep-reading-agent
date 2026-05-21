"""Shared HTML rendering for protected Markdown previews."""
from __future__ import annotations

from html import escape

import markdown


def render_markdown_preview_html(content: str, filename: str) -> str:
    html_content = markdown.markdown(content, extensions=["tables", "fenced_code"])
    safe_filename = escape(filename)
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{safe_filename}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 800px;
            margin: 0 auto;
            padding: 40px 20px;
            line-height: 1.8;
            color: #333;
            background: #fff;
        }}
        h1 {{ color: #059669; border-bottom: 2px solid #e5e7eb; padding-bottom: 10px; }}
        h2 {{ color: #374151; margin-top: 30px; }}
        h3 {{ color: #4b5563; }}
        code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }}
        pre {{ background: #f9fafb; padding: 16px; border-radius: 8px; overflow-x: auto; }}
        pre code {{ background: none; padding: 0; }}
        table {{ border-collapse: collapse; width: 100%; margin: 16px 0; }}
        th, td {{ border: 1px solid #e5e7eb; padding: 8px 12px; text-align: left; }}
        th {{ background: #f9fafb; font-weight: 600; }}
        blockquote {{ border-left: 4px solid #059669; margin: 16px 0; padding-left: 16px; color: #4b5563; }}
        hr {{ border: none; border-top: 1px solid #e5e7eb; margin: 30px 0; }}
    </style>
</head>
<body>
    <h1>{safe_filename}</h1>
    {html_content}
</body>
</html>"""
