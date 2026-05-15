import os
import re
import json
import time


def sanitize_filename(name: str) -> str:
    """Sanitize filename for filesystem"""
    # Remove extension
    name = os.path.splitext(name)[0]
    # Replace invalid chars
    name = re.sub(r'[<>:"/\|?*]', '_', name)
    # Limit length
    if len(name) > 100:
        name = name[:100]
    return name


def extract_metadata(paper_text: str, api_key: str) -> dict:
    """Extract paper metadata using DeepSeek API"""
    try:
        from openai import OpenAI
        import httpx
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=httpx.Timeout(connect=30.0, read=120.0, write=30.0, pool=30.0),
        )
        
        prompt = f"""请从以下论文的前两页内容中，提取论文元数据。
只返回 JSON，不要任何其他文字：

{{"title":"完整标题", "authors":["作者1","作者2"], "journal":"期刊名", "year":2024, "volume":"", "issue":"", "pages":"", "doi":""}}

无法确定则设为 null。

论文内容：
{paper_text[:3000]}
"""
        response = client.chat.completions.create(
            model="deepseek-v4-flash",
            extra_body={"thinking": {"type": "disabled"}},
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=500
        )
        content = response.choices[0].message.content
        match = re.search(r'\{.*\}', content, re.DOTALL)
        if match:
            return json.loads(match.group())
        return {}
    except Exception as e:
        print(f"Metadata extraction failed: {e}")
        return {}


def build_frontmatter(metadata: dict, reading_type: str) -> str:
    """Build YAML frontmatter from metadata dict"""
    lines = ["---"]
    
    title = metadata.get("title", "")
    if title:
        lines.append(f'title: "{title}"')
    
    authors = metadata.get("authors", [])
    if authors:
        lines.append(f'authors: {authors}')
    
    if metadata.get("journal"):
        lines.append(f'journal: "{metadata["journal"]}"')
    if metadata.get("year"):
        lines.append(f'year: {metadata["year"]}')
    if metadata.get("volume"):
        lines.append(f'volume: "{metadata["volume"]}"')
    if metadata.get("issue"):
        lines.append(f'issue: "{metadata["issue"]}"')
    if metadata.get("pages"):
        lines.append(f'pages: "{metadata["pages"]}"')
    if metadata.get("doi"):
        lines.append(f'doi: "{metadata["doi"]}"')
    
    lines.append(f'reading_type: "{reading_type}"')
    lines.append(f'reading_date: "{time.strftime("%Y-%m-%d")}"')
    lines.append("---")
    lines.append("")
    
    return "\n".join(lines)
