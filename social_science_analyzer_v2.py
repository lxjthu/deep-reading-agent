import os
import sys
import argparse
import json
import logging
import re
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

class SocialScienceAnalyzerV2:
    """使用 Markdown 格式输出的社会科学分析器 (v2)"""
    
    def __init__(self, model_name="deepseek-reasoner", base_url="https://api.deepseek.com"):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment")
        self.client = OpenAI(api_key=self.api_key, base_url=base_url)
        self.model_name = model_name
    
    def _load_prompt_from_file(self, layer: str) -> str:
        """
        从外部文件加载提示词
        
        Args:
            layer: 层级标识 (L1_Context / L2_Theory / L3_Logic / L4_Value)
        
        Returns:
            提示词字符串 (完整 Markdown 内容)
        """
        prompts_dir = os.path.join(os.path.dirname(__file__), "prompts", "qual_analysis")
        prompt_file = os.path.join(prompts_dir, f"{layer}_Prompt.md")
        
        if not os.path.exists(prompt_file):
            logger.error(f"Prompt file not found: {prompt_file}")
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
        
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            logger.info(f"Loaded prompt from file: {layer}")
            return content
                
        except Exception as e:
            logger.error(f"Error loading prompt file: {e}")
            raise
    
    def _call_llm_markdown(self, system_prompt: str, user_content: str) -> str:
        """
        调用 LLM 并直接返回 Markdown 格式输出
        
        Args:
            system_prompt: 系统提示词
            user_content: 用户内容
        
        Returns:
            Markdown 格式的分析结果
        """
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.1,
                stream=False,
                max_tokens=8000
            )
            markdown_content = response.choices[0].message.content
            logger.info(f"LLM call successful, returned {len(markdown_content)} characters")
            return markdown_content
            
        except Exception as e:
            logger.error(f"LLM Call Error: {e}")
            return None
    
    def _extract_genre_from_l1_markdown(self, l1_markdown: str) -> str:
        """
        从 L1 Markdown 输出中提取研究体裁
        
        Args:
            l1_markdown: L1 层的 Markdown 输出
        
        Returns:
            体裁字符串 (Case Study / Theoretical / QCA / Quantitative / Review)
        """
        # 查找 "## 1. 论文分类" 下的内容
        match = re.search(r'##\s+1\.\s+论文分类\s*\n+(.+?)(?=##\s+\d+\.|\Z)', 
                        l1_markdown, re.DOTALL)
        
        if match:
            content = match.group(1).strip()
            # 常见体裁映射
            genre_map = {
                "案例研究": "Case Study",
                "理论构建": "Theoretical",
                "定性比较分析": "QCA",
                "定量研究": "Quantitative",
                "文献综述": "Review"
            }
            
            for cn, en in genre_map.items():
                if cn in content:
                    logger.info(f"Extracted genre from L1: {en}")
                    return en
            
            # 如果是英文直接返回
            if content in ["Case Study", "Theoretical", "QCA", "Quantitative", "Review"]:
                return content
        
        # 默认返回
        logger.warning("Could not extract genre from L1, using default: Theoretical")
        return "Theoretical"
    
    def analyze_l1_context(self, text_segment: str) -> str:
        """
        L1 层分析：背景层
        
        Args:
            text_segment: L1 层的文本内容
        
        Returns:
            Markdown 格式的分析结果
        """
        # 加载提示词
        prompt = self._load_prompt_from_file("L1_Context")
        
        # 构建系统提示词（强调 Markdown 输出）
        system_prompt = f"""{prompt}

IMPORTANT: 请严格按照上述"输出格式"部分的Markdown格式输出，不要输出JSON格式。
直接输出Markdown格式的结构化内容即可。
"""
        
        # 构建用户提示词
        user_prompt = f"""以下是论文的L1_Context（背景层）内容：

{text_segment}

请按照提示词要求进行分析，并直接输出Markdown格式的分析结果。"""
        
        # 调用 LLM
        return self._call_llm_markdown(system_prompt, user_prompt)
    
    def analyze_l2_theory(self, text_segment: str) -> str:
        """
        L2 层分析：理论层
        
        Args:
            text_segment: L2 层的文本内容
        
        Returns:
            Markdown 格式的分析结果
        """
        # 加载提示词
        prompt = self._load_prompt_from_file("L2_Theory")
        
        # 构建系统提示词
        system_prompt = f"""{prompt}

IMPORTANT: 请严格按照上述"输出格式"部分的Markdown格式输出，不要输出JSON格式。
直接输出Markdown格式的结构化内容即可。
"""
        
        # 构建用户提示词
        user_prompt = f"""以下是论文的L2_Theory（理论层）内容：

{text_segment}

请按照提示词要求进行分析，并直接输出Markdown格式的分析结果。"""
        
        # 调用 LLM
        return self._call_llm_markdown(system_prompt, user_prompt)
    
    def analyze_l3_logic(self, text_segment: str, genre: str) -> str:
        """
        L3 层分析：逻辑层（根据体裁自适应）
        
        Args:
            text_segment: L3 层的文本内容
            genre: 研究体裁 (Theoretical / Case Study / QCA / Quantitative / Review)
        
        Returns:
            Markdown 格式的分析结果
        """
        # 加载提示词
        prompt = self._load_prompt_from_file("L3_Logic")
        
        # 替换 {genre} 变量
        prompt = prompt.replace("{genre}", genre)
        
        # 构建系统提示词
        system_prompt = f"""{prompt}

IMPORTANT: 请严格按照上述"输出格式"部分的Markdown格式输出，不要输出JSON格式。
直接输出Markdown格式的结构化内容即可。
"""
        
        # 构建用户提示词
        user_prompt = f"""以下是论文的L3_Logic（逻辑层）内容：

{text_segment}

请按照提示词要求进行分析，并直接输出Markdown格式的分析结果。"""
        
        # 调用 LLM
        return self._call_llm_markdown(system_prompt, user_prompt)
    
    def analyze_l4_value(self, text_segment: str) -> str:
        """
        L4 层分析：价值层
        
        Args:
            text_segment: L4 层的文本内容
        
        Returns:
            Markdown 格式的分析结果
        """
        # 加载提示词
        prompt = self._load_prompt_from_file("L4_Value")
        
        # 构建系统提示词
        system_prompt = f"""{prompt}

IMPORTANT: 请严格按照上述"输出格式"部分的Markdown格式输出，不要输出JSON格式。
直接输出Markdown格式的结构化内容即可。
"""
        
        # 构建用户提示词
        user_prompt = f"""以下是论文的L4_Value（价值层）内容：

{text_segment}

请按照提示词要求进行分析，并直接输出Markdown格式的分析结果。"""
        
        # 调用 LLM
        return self._call_llm_markdown(system_prompt, user_prompt)
    
    def save_layer_markdown(self, markdown_content: str, layer: str, 
                           basename: str, output_dir: str) -> str:
        """
        保存单层的 Markdown 分析结果
        
        Args:
            markdown_content: Markdown 内容
            layer: 层级名称 (L1_Context / L2_Theory / L3_Logic / L4_Value)
            basename: 论文基础名称
            output_dir: 输出目录
        
        Returns:
            保存的文件路径
        """
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{layer}.md"
        path = os.path.join(output_dir, filename)
        
        with open(path, 'w', encoding='utf-8') as f:
            f.write(markdown_content)
        
        logger.info(f"Saved {layer} to {path}")
        return path
    
    def generate_full_report(self, layer_outputs: dict, basename: str, 
                           output_dir: str) -> str:
        """
        生成完整的 4 层分析总报告
        
        Args:
            layer_outputs: 各层输出 {"L1_Context": markdown, ...}
            basename: 论文基础名称
            output_dir: 输出目录
        
        Returns:
            保存的文件路径
        """
        os.makedirs(output_dir, exist_ok=True)
        filename = f"{basename}_Full_Report.md"
        path = os.path.join(output_dir, filename)
        
        with open(path, 'w', encoding='utf-8') as f:
            # 写入标题
            f.write(f"# 社会科学深度阅读报告：{basename}\n\n")
            f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
            
            # 合并各层内容
            layers = ["L1_Context", "L2_Theory", "L3_Logic", "L4_Value"]
            layer_titles = {
                "L1_Context": "第一层：背景层分析 (L1_Context)",
                "L2_Theory": "第二层：理论层分析 (L2_Theory)",
                "L3_Logic": "第三层：逻辑层分析 (L3_Logic)",
                "L4_Value": "第四层：价值层分析 (L4_Value)"
            }
            
            for layer in layers:
                if layer in layer_outputs:
                    f.write(f"## {layer_titles[layer]}\n\n")
                    f.write(layer_outputs[layer])
                    f.write("\n\n---\n\n")
        
        logger.info(f"Saved Full Report to {path}")
        return path


def load_segmented_md(path: str) -> dict:
    """
    Parse a markdown file into sections.
    Supports raw extraction output (# and ## headers), traditional segmented format,
    and Smart Router QUAL format (L1-L4).
    Strips YAML frontmatter before parsing.
    Falls back to {"Full Text": content} if no sections found.
    """
    sections = {}
    current_section = None
    buffer = []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Strip YAML frontmatter
    content = re.sub(r'^---\n.*?\n---\n', '', content, flags=re.DOTALL)

    # Detect Smart Router QUAL format
    is_smart_router_qual = "- Mode: qual" in content

    for line in content.split('\n'):
        if line.startswith("## "):
            if current_section is not None and buffer:
                sections[current_section] = "\n".join(buffer)
            current_section = line.lstrip("# ").strip()
            buffer = []
        elif line.startswith("# ") and not line.startswith("## "):
            if current_section is not None and buffer:
                sections[current_section] = "\n".join(buffer)
            current_section = line.lstrip("# ").strip()
            buffer = []
        else:
            buffer.append(line)

    if current_section is not None and buffer:
        sections[current_section] = "\n".join(buffer)

    # If Smart Router QUAL format, extract L1-L4 content from code blocks
    if is_smart_router_qual:
        sections = _extract_smart_router_qual_sections(sections)

    # Fallback: if no sections found, use full text
    if not sections:
        stripped = content.strip()
        if stripped:
            sections["Full Text"] = stripped

    return sections


def _extract_smart_router_qual_sections(sections: dict) -> dict:
    """
    从 Smart Router QUAL 格式中提取 L1-L4 层级的实际文本内容
    """
    extracted = {}
    layer_mapping = {
        "L1. L1_Context (背景层)": "L1_Context",
        "L2. L2_Theory (理论层)": "L2_Theory",
        "L3. L3_Logic (逻辑层)": "L3_Logic",
        "L4. L4_Value (价值层)": "L4_Value"
    }
    
    for layer_title, layer_key in layer_mapping.items():
        if layer_title in sections:
            content = sections[layer_title]
            # 提取 ```text ... ``` 代码块中的内容
            text_blocks = re.findall(r'```text\s*\n(.*?)\n```', content, re.DOTALL)
            if text_blocks:
                extracted[layer_key] = "\n\n".join(text_blocks)
            else:
                # 如果没有代码块，直接使用原内容
                extracted[layer_key] = content
    
    logger.info(f"Extracted {len(extracted)} layers from Smart Router QUAL format")
    return extracted


def get_combined_text(sections: dict, keys: list) -> str:
    """
    根据关键词组合章节内容
    
    Args:
        sections: 所有章节
        keys: 关键词列表
    
    Returns:
        组合后的文本
    """
    text = ""
    for k, v in sections.items():
        if k and v and any(key.lower() in k.lower() for key in keys):
            text += v + "\n"
    
    # 如果没有匹配，返回前 30000 字符
    return text if text else "".join(sections.values())[:30000]


def main():
    parser = argparse.ArgumentParser(description="Social Science 4-Layer Analyzer v2 (Markdown Output)")
    parser.add_argument("segmented_dir", help="Directory containing Segmented MD files")
    parser.add_argument("--out_dir", default="social_science_results_v2", help="Output directory")
    parser.add_argument("--filter", nargs="+", help="Keywords to filter filenames")
    args = parser.parse_args()

    analyzer = SocialScienceAnalyzerV2()
    os.makedirs(args.out_dir, exist_ok=True)
    
    # 查找目标文件 (accept extraction or segmented outputs)
    EXTRACTION_SUFFIXES = ("_paddleocr.md", "_raw.md", "_segmented.md")
    all_files = [f for f in os.listdir(args.segmented_dir) if any(f.endswith(s) for s in EXTRACTION_SUFFIXES)]
    target_files = []

    if args.filter:
        logger.info(f"Filtering files with keywords: {args.filter}")
        for f in all_files:
            if any(k in f for k in args.filter):
                target_files.append(f)
    else:
        target_files = all_files

    logger.info(f"Found {len(target_files)} files to analyze.")

    all_results = []

    for filename in target_files:
        basename = os.path.splitext(filename)[0]
        for suffix in ("_segmented", "_paddleocr", "_raw"):
            if basename.endswith(suffix):
                basename = basename[:-len(suffix)]
                break
        file_path = os.path.join(args.segmented_dir, filename)
        logger.info(f"Processing {basename}...")
        
        sections = load_segmented_md(file_path)
        
        # 检查是否为 Smart Router QUAL 格式（已提取 L1-L4）
        if "L1_Context" in sections:
            logger.info("Using Smart Router QUAL format - L1-L4 already extracted")
            text_l1 = sections.get("L1_Context", "")
            text_l2 = sections.get("L2_Theory", "")
            text_l3 = sections.get("L3_Logic", "")
            text_l4 = sections.get("L4_Value", "")
        else:
            # 传统格式：使用关键词匹配
            text_l1 = get_combined_text(sections, ["abstract", "introduction", "background", "摘要", "引言", "背景", "绪论", "问题提出"])
            
            # L1 空内容处理
            if len(text_l1) < 200:
                keys = list(sections.keys())
                if keys:
                    text_l1 = sections[keys[0]]
                    if len(keys) > 1:
                        text_l1 += "\n" + sections[keys[1]]
            
            text_l2 = get_combined_text(sections, ["literature", "theory", "theoretical", "文献", "综述", "理论", "基础", "研究现状"])
            text_l3 = get_combined_text(sections, ["method", "result", "finding", "case", "analysis", "方法", "设计", "案例", "结果", "分析", "实证", "模型", "路径", "机制"])
            text_l4 = get_combined_text(sections, ["discussion", "conclusion", "implication", "讨论", "结论", "启示", "展望", "建议", "结语"])
        
        # 执行 4 层分析
        logger.info("Analyzing L1_Context...")
        l1_markdown = analyzer.analyze_l1_context(text_l1)
        
        # 从 L1 提取体裁
        genre = analyzer._extract_genre_from_l1_markdown(l1_markdown)
        logger.info(f"Detected genre: {genre}")
        
        logger.info("Analyzing L2_Theory...")
        l2_markdown = analyzer.analyze_l2_theory(text_l2)
        
        logger.info(f"Analyzing L3_Logic (Genre: {genre})...")
        l3_markdown = analyzer.analyze_l3_logic(text_l3, genre=genre)
        
        logger.info("Analyzing L4_Value...")
        l4_markdown = analyzer.analyze_l4_value(text_l4)
        
        # 保存各层结果
        paper_out_dir = os.path.join(args.out_dir, basename)
        os.makedirs(paper_out_dir, exist_ok=True)
        
        analyzer.save_layer_markdown(l1_markdown, "L1_Context", basename, paper_out_dir)
        analyzer.save_layer_markdown(l2_markdown, "L2_Theory", basename, paper_out_dir)
        analyzer.save_layer_markdown(l3_markdown, "L3_Logic", basename, paper_out_dir)
        analyzer.save_layer_markdown(l4_markdown, "L4_Value", basename, paper_out_dir)
        
        # 生成总报告
        layer_outputs = {
            "L1_Context": l1_markdown,
            "L2_Theory": l2_markdown,
            "L3_Logic": l3_markdown,
            "L4_Value": l4_markdown
        }
        analyzer.generate_full_report(layer_outputs, basename, paper_out_dir)
        
        all_results.append({
            "basename": basename,
            "genre": genre,
            "layer_outputs": layer_outputs
        })
        
        logger.info(f"Completed analysis for {basename}\n")

    logger.info(f"Batch analysis complete. Processed {len(all_results)} papers.")


if __name__ == "__main__":
    main()
