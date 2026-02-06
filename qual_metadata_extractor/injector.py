"""
Frontmatter 注入模块
"""

import logging
import yaml

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def inject_qual_frontmatter(md_content: str, metadata: dict) -> str:
    """
    为 QUAL 分析文件注入 YAML Frontmatter
    
    Args:
        md_content: 原始 Markdown 内容
        metadata: 元数据字典
    
    Returns:
        注入后的 Markdown 内容
    """
    # 直接使用提供的元数据，不与现有 frontmatter 合并
    # 生成 YAML Frontmatter
    yaml_str = yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).strip()
    frontmatter_block = f"---\n{yaml_str}\n---\n\n"
    
    # 移除现有 frontmatter（如果有）
    body_content = md_content
    if md_content.startswith("---\n"):
        end_idx = md_content.find("\n---\n", 4)
        if end_idx != -1:
            body_content = md_content[end_idx + 5:]
    
    logger.info("Injected frontmatter")
    return frontmatter_block + body_content


def add_qual_navigation_links(md_content: str, layer: str, paper_name: str, all_layers: list) -> str:
    """
    为 QUAL 分析文件添加导航链接
    
    Args:
        md_content: Markdown 内容
        layer: 当前层级（如 "L1_Context", "Full_Report"）
        paper_name: 论文名称
        all_layers: 所有层级列表 ["L1_Context", "L2_Theory", "L3_Logic", "L4_Value"]
    
    Returns:
        添加导航后的内容
    """
    # Full_Report 不添加导航
    if layer == "Full_Report" or not all_layers:
        return md_content
    
    # 检查是否已有导航
    if "## 导航" in md_content or "## Navigation" in md_content:
        return md_content
    
    # 生成导航段落
    navigation = "\n\n## 导航\n\n"
    
    # 链接到总报告
    full_report_name = f"{paper_name}_Full_Report"
    navigation += f"**返回总报告**：[[{full_report_name}]]\n\n"
    
    # 链接到其他层级
    other_layers = [l for l in all_layers if l != layer]
    if other_layers:
        navigation += "**其他层级**：\n"
        for l in other_layers:
            navigation += f"- [[{l}]]\n"
    
    logger.info(f"Added navigation links for {layer}")
    return md_content + navigation


def save_with_metadata(file_path: str, content: str, metadata: dict, layer: str, paper_name: str, all_layers: list):
    """
    保存文件并注入元数据和导航
    
    Args:
        file_path: 文件路径
        content: 原始内容
        metadata: 元数据字典（如果为 None，则不注入 frontmatter，只添加导航）
        layer: 当前层级
        paper_name: 论文名称
        all_layers: 所有层级列表
    """
    # 注入 Frontmatter（如果有元数据）
    if metadata:
        new_content = inject_qual_frontmatter(content, metadata)
    else:
        new_content = content
    
    # Full_Report 移除现有导航（如果有），不添加新导航
    if layer == "Full_Report":
        # 移除 ## 导航 部分
        if "## 导航" in new_content:
            # 找到导航部分
            nav_idx = new_content.find("## 导航")
            # 找到导航部分之前的换行
            prev_newline = new_content.rfind("\n\n", 0, nav_idx)
            if prev_newline != -1:
                new_content = new_content[:prev_newline]
            else:
                new_content = new_content[:nav_idx]
    # 其他层级文件添加导航
    elif all_layers:
        new_content = add_qual_navigation_links(new_content, layer, paper_name, all_layers)
    
    # 保存
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    logger.info(f"Saved {file_path} with metadata and navigation")
