"""
第一次提取：从生成的 MD 报告中提取 `## 数字. 标题` 格式的章节
用 DeepSeek 进行 30-50 字总结
"""

import os
import re
import logging
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def get_deepseek_client():
    """获取 DeepSeek 客户端"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        logger.error("DEEPSEEK_API_KEY not found in environment")
        return None
    return OpenAI(api_key=api_key, base_url="https://api.deepseek.com")


def extract_sections_from_markdown(md_content: str) -> dict:
    """
    从 QUAL 分析的 Markdown 中提取 `## 数字. 标题` 格式的章节
    
    Args:
        md_content: Markdown 内容
    
    Returns:
        {
            "1. 论文分类": "完整内容...",
            "2. 核心问题": "完整内容...",
            ...
        }
    """
    sections = {}
    current_num = None
    current_title = None
    current_content = []
    
    for line in md_content.split('\n'):
        # 匹配 ## 数字. 标题（注意：## 和数字之间有空格）
        match = re.match(r'^##\s+(\d+)\.\s+(.+)$', line)
        if match:
            # 保存上一个章节
            if current_num and current_title:
                key = f"{current_num}. {current_title}"
                sections[key] = '\n'.join(current_content).strip()
            
            # 开始新章节
            current_num = match.group(1)
            current_title = match.group(2).strip()
            current_content = []
        elif line.startswith('#'):
            # 遇到其他标题（如 # 一级标题），跳过
            continue
        else:
            if current_num and current_title:
                current_content.append(line)
    
    # 保存最后一个章节
    if current_num and current_title:
        key = f"{current_num}. {current_title}"
        sections[key] = '\n'.join(current_content).strip()
    
    logger.info(f"Extracted {len(sections)} sections from markdown")
    return sections


def summarize_section_with_deepseek(client, title: str, content: str) -> str:
    """
    用 DeepSeek 将章节内容总结为 30-50 字中文
    
    Args:
        client: DeepSeek 客户端
        title: 章节标题（如 "1. 论文分类"）
        content: 章节完整内容
    
    Returns:
        30-50 字以内的中文摘要
    """
    if len(content) < 50:
        # 内容太短，直接截取
        summary = content[:50].strip()
        logger.info(f"Section '{title}' too short ({len(content)} chars), truncated to 50 chars")
        return summary
    
    # 计算合适的总结长度（30-50字）
    target_length = min(50, max(30, len(content) // 10))
    
    prompt = f"""请将以下内容总结为{target_length}字以内的一句话：
标题：{title}
内容：{content}

要求：
- 中文输出
- {target_length}字以内
- 抓住核心要点
- 保持学术准确性
"""
    
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个精确的学术内容总结专家。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=150
        )
        summary = resp.choices[0].message.content.strip()
        
        # 确保不超过目标长度
        if len(summary) > target_length:
            summary = summary[:target_length].strip()
        
        logger.info(f"Summarized '{title}': {len(summary)} chars")
        return summary
        
    except Exception as e:
        logger.error(f"Summary failed for {title}: {e}")
        # 降级：截取前 50 字
        return content[:50].strip()


def extract_layer_subsections(layer_name: str, md_content: str, deepseek_client) -> dict:
    """
    提取单个层的所有子章节元数据
    
    Args:
        layer_name: 层级名称（如 "L1_Context"）
        md_content: Markdown 内容
        deepseek_client: DeepSeek 客户端
    
    Returns:
        {
            "1. 论文分类": "30-50字摘要",
            "2. 核心问题": "30-50字摘要",
            ...
        }
    """
    logger.info(f"Extracting subsections from {layer_name}...")
    
    # 提取章节
    sections = extract_sections_from_markdown(md_content)
    
    if not sections:
        logger.warning(f"No sections found in {layer_name}")
        return {}
    
    # 总结每个章节
    subsections_meta = {}
    for title, content in sections.items():
        if len(content) >= 50:  # 仅总结足够长的章节
            summary = summarize_section_with_deepseek(deepseek_client, title, content)
            subsections_meta[title] = summary
        else:
            logger.info(f"Section '{title}' too short ({len(content)} chars), skipping summary")
    
    logger.info(f"Extracted {len(subsections_meta)} subsections from {layer_name}")
    return subsections_meta
