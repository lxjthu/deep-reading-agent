# Third-party dependencies

The offline reader vendors KaTeX **0.16.22** JavaScript, CSS and fonts in `assets/reader/katex/`. Upstream: https://github.com/KaTeX/KaTeX/releases/tag/v0.16.22 ; distribution: https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/ . KaTeX is MIT licensed; its copyright and full license are retained in `assets/reader/katex/LICENSE`. The browser uses these local assets and makes no CDN request.

Reader Python dependencies pinned in `requirements.txt`:

| Package | Version | Upstream | License |
| --- | --- | --- | --- |
| Markdown | 3.10.2 | https://github.com/Python-Markdown/markdown | BSD-3-Clause |
| nh3 | 0.3.3 | https://github.com/messense/nh3 | MIT |
| python-markdown-math | 0.9 | https://github.com/mitya57/python-markdown-math | BSD-3-Clause |

Other skill runtime dependencies retain the ranges in `requirements.txt`: PyMuPDF >=1.24,<2 (AGPL-3.0 or commercial license), httpx >=0.27,<1 (BSD-3-Clause), and openpyxl >=3.1,<4 (MIT). They are installed separately, not copied into the reader snapshot.
