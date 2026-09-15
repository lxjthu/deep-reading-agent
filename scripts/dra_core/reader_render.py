"""Offline Markdown rendering; untrusted HTML is sanitized before entering a page."""
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit, unquote
import hashlib
import re
import shutil


def render(text, source=None, output=None, allowed_root=None, namespace="document", image_map=None):
    import markdown
    import nh3
    warnings = []
    # Keep YAML available as text, never execute or interpolate its fields.
    front = re.match(r'\A---\s*\n(.*?)\n---\s*(?:\n|$)', text, re.S)
    metadata = ''
    if front:
        metadata = '<details><summary>文档元信息</summary><pre>'+escape(front[1])+'</pre></details>'
        text = text[front.end():]
    md = markdown.Markdown(extensions=['extra', 'toc', 'sane_lists', 'mdx_math'],
                           extension_configs={'mdx_math': {'enable_dollar_delimiter': True}})
    body = md.convert(text)
    # Math is inert escaped data until the local, trust:false KaTeX renderer sees it.
    body = re.sub(r'<script type="math/tex(; mode=display)?">(.*?)</script>',
                  lambda m: '<span class="math" data-display="'+('true' if m[1] else 'false')+'" data-tex="'+escape(m[2], quote=True)+'">'+escape(m[2])+'</span>', body, flags=re.S)

    def attribute(tag, name, value):
        if name == 'src':
            parsed = urlsplit(value)
            if tag != 'img' or parsed.scheme or parsed.netloc or not source or not output:
                warnings.append('已阻止外部或不可用图片：'+value); return None
            unresolved = (Path(source).parent / unquote(parsed.path))
            if image_map is not None:
                unresolved = image_map.get(unquote(parsed.path))
                if unresolved is None:
                    warnings.append('图片未列入来源清单：'+value); return None
                unresolved = Path(unresolved)
            if unresolved.is_symlink() or any(p.is_symlink() for p in unresolved.parents):
                warnings.append('已阻止符号链接图片：'+value); return None
            candidate = unresolved.resolve()
            root = Path(allowed_root or Path(source).parent).resolve()
            if not candidate.is_relative_to(root) or not candidate.is_file() or candidate.suffix.lower() not in {'.png','.jpg','.jpeg','.gif','.webp'}:
                warnings.append('未复制越界、缺失或不支持的图片：'+value); return None
            name = hashlib.sha256(candidate.read_bytes()).hexdigest()+candidate.suffix.lower()
            target = Path(output)/'media'/name; target.parent.mkdir(exist_ok=True)
            shutil.copyfile(candidate,target)
            return 'media/'+name
        if name == 'href':
            parsed = urlsplit(value)
            if value.startswith('#') or parsed.scheme in {'http','https','mailto'}: return value
            return None
        return value

    tags = set(nh3.ALLOWED_TAGS) | {'h1','h2','h3','h4','h5','h6','table','thead','tbody','tfoot','tr','td','th','sup','sub','span','div'}
    attrs = {'*': {'id','class','title'}, 'a': {'href'}, 'img': {'src','alt','title'},
             'td': {'rowspan','colspan'}, 'th': {'rowspan','colspan','scope'},
             'span': {'data-tex','data-display'}}
    body = nh3.clean(body, tags=tags, attributes=attrs, attribute_filter=attribute,
                     url_schemes={'http','https','mailto'}, clean_content_tags={'script','style','iframe','object','svg','math'})
    body = re.sub(r'<img\b[^>]*>',lambda m:m[0] if re.search(r'\bsrc=',m[0]) else '<span class="media-missing">图片未包含在快照中；请查看来源记录。</span>',body)
    body = body.replace('<table>', '<div class="table-scroll"><table>').replace('</table>', '</table></div>')
    toc = nh3.clean(md.toc, attributes={'*':{'class'},'a':{'href'}},url_schemes={'http','https'})
    # Namespace all anchors, including footnotes, so comparison copies remain unique.
    ids = {}
    def identify(match):
        old = match[1]; count = ids.get(old, 0); ids[old] = count + 1
        return 'id="'+escape(namespace+'-'+old+('-'+str(count) if count else ''), quote=True)+'"'
    body = re.sub(r'id="([^"]+)"', identify, body)
    body = re.sub(r'href="#([^"]+)"', lambda m: 'href="#'+escape(namespace+'-'+m[1], quote=True)+'"', body)
    toc = re.sub(r'href="#([^"]+)"', lambda m: 'href="#'+escape(namespace+'-'+m[1], quote=True)+'"', toc)
    return {'html':metadata+body, 'toc':toc, 'warnings':warnings}
