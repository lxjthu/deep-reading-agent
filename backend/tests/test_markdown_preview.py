from __future__ import annotations

import unittest

from backend.services.markdown_preview import render_markdown_preview_html


class MarkdownPreviewTests(unittest.TestCase):
    def test_markdown_preview_renders_mathjax_config_without_fstring_errors(self) -> None:
        content = """# Title

Inline $x+1$ and block:

$$y=x^2$$
"""
        html = render_markdown_preview_html(content, "math.md")

        self.assertIn("window.MathJax", html)
        self.assertIn("tex:", html)
        self.assertIn("mathjax@3", html)
        self.assertIn("math.md", html)


if __name__ == "__main__":
    unittest.main()
