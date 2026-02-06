import os
import sys
import argparse
import json
import logging
import pandas as pd
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
import json_repair

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

class SocialScienceAnalyzer:
    def __init__(self, model_name="deepseek-chat", base_url="https://api.deepseek.com"):
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
            提示词字符串
        """
        prompts_dir = os.path.join(os.path.dirname(__file__), "prompts", "qual_analysis")
        prompt_file = os.path.join(prompts_dir, f"{layer}_Prompt.md")
        
        if not os.path.exists(prompt_file):
            logger.warning(f"Prompt file not found: {prompt_file}, using fallback")
            return None
        
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 提取 ```text ... ``` 代码块
            start_idx = content.find("```text") + 8
            end_idx = content.find("```", start_idx)
            
            if start_idx != -1 and end_idx != -1:
                prompt_text = content[start_idx:end_idx].strip()
                logger.info(f"Loaded prompt from file: {layer}")
                return prompt_text
            else:
                logger.warning(f"Failed to extract code block from: {prompt_file}")
                return None
                
        except Exception as e:
            logger.error(f"Error loading prompt file: {e}")
            return None
    
    def _call_llm(self, system_prompt: str, user_content: str, fallback_prompt: str = None, use_dynamic_prompt: bool = True) -> dict:
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=4000
            )
            content = response.choices[0].message.content
            result = json_repair.repair_json(content, return_objects=True)
            
            # 记录是否使用动态加载的提示词
            if use_dynamic_prompt:
                logger.info(f"Using dynamically loaded prompt")
            elif fallback_prompt:
                logger.warning(f"Using fallback prompt for: {fallback_prompt}")
            
            return result
        except Exception as e:
            logger.error(f"LLM Call Error: {e}")
            return {}

    def analyze_l1_context(self, text_segment: str) -> dict:
        # 尝试从文件加载提示词
        prompt = self._load_prompt_from_file("L1_Context")
        
        # 如果文件不存在或加载失败，使用备用硬编码提示词
        if not prompt:
            prompt = """
    You are a Social Science Context Analyst. Extract Metadata, Policy Context, and Status Data.
    Focus on "Introduction" and "Background" sections.
    IMPORTANT: ALL OUTPUT MUST BE IN CHINESE (SIMPLIFIED).
    
    REQUIREMENTS:
    1. **Genre**: Classify as 'Case Study', 'QCA', 'Review', 'Quantitative', or 'Theoretical'.
    2. **Policies**: List ALL specific policy documents mentioned (Name, Year, Level, Core Content). Be precise.
    3. **Status Data**: Extract key statistical data describing the status quo (e.g., GEP value, investment amount).
    
    Output JSON:
    {
        "metadata": {
            "title": "...", "authors": "...", "year": "...", "journal": "...", "genre": "..."
        },
        "policy_context": [
            {"name": "...", "year": "...", "level": "Central/Local", "content": "..."}
        ],
        "status_data": [
            {"item": "...", "value": "...", "unit": "...", "context": "..."}
        ],
        "detailed_analysis": "A 300-word detailed narrative of context and background in Chinese."
    }
    """
        
        return self._call_llm(prompt, text_segment, fallback_prompt="L1_Context (FALLBACK)")

    def analyze_l2_theory(self, text_segment: str) -> dict:
        # 尝试从文件加载提示词
        prompt = self._load_prompt_from_file("L2_Theory")
        
        # 如果文件不存在或加载失败，使用备用硬编码提示词
        if not prompt:
            prompt = """
    You are a Social Science Theory Analyst. Extract Theoretical Foundations and Constructs.
    Focus on "Literature Review" and "Theoretical Framework" sections.
    IMPORTANT: ALL OUTPUT MUST BE IN CHINESE (SIMPLIFIED).
    
    REQUIREMENTS:
    1. **Past Theories**: Summarize classic theories reviewed (e.g., Externalities).
    2. **Key Constructs**: List core concepts and their EXACT definitions from the text.
    3. **Relationships**: Describe how constructs interact (hypothesized relationships).
    4. **Framework**: Describe the theoretical framework built in this paper.
    
    Output JSON:
    {
        "past_theories": [{"name": "...", "summary": "..."}],
        "key_constructs": [{"name": "...", "definition": "..."}],
        "relationships": [{"from": "...", "to": "...", "mechanism": "..."}],
        "framework_desc": "...",
        "detailed_analysis": "A 400-word deep dive into theoretical logic and construct definitions in Chinese."
    }
    """
        
        return self._call_llm(prompt, text_segment, fallback_prompt="L2_Theory (FALLBACK)")

    def analyze_l3_logic(self, text_segment: str, genre: str) -> dict:
        # 尝试从文件加载提示词
        prompt = self._load_prompt_from_file("L3_Logic")
        
        # 如果文件不存在或加载失败，使用备用硬编码提示词
        if not prompt:
             prompt = f"""
    You are a Social Science Logic Analyst. Extract Core Mechanism or Path.
    The paper genre is: {genre}.
    Focus on "Methodology", "Case Description", and "Results" sections.
    IMPORTANT: ALL OUTPUT MUST BE IN CHINESE (SIMPLIFIED).

    REQUIREMENTS based on genre:
    - If **Case Study**: Extract "Process Model" (Phases, Events, Strategies).
    - If **QCA/Quant**: Extract "Causal Paths/Configurations" or "Hypothesis Results".
    - If **Review**: Extract "Integrated Framework" or "Evolution Map".

    Output JSON:
    {{
        "core_mechanism": {{
            "type": "{genre} Logic",
            "components": [
                {{"phase_or_path": "...", "description": "...", "evidence": "..."}
            ]
        }},
        "detailed_analysis": "A 500-word detailed narrative of core mechanism/findings in Chinese. Be very specific."
    }}
    """
        
        return self._call_llm(prompt, text_segment, fallback_prompt="L3_Logic (FALLBACK)")

    def analyze_l1_context(self, text_segment: str) -> dict:
        # 尝试从文件加载提示词
        prompt = self._load_prompt_from_file("L1_Context")
        
        # 如果文件不存在或加载失败，使用备用硬编码提示词
        if not prompt:
            prompt = """
    你是一位具有深厚理论功底和实践经验的社会科学研究学者。你的任务是从引言和背景章节中提取关键信息，为后续的理论分析奠定基础。请注意，基础元数据（标题、作者、期刊、年份）将由专门的视觉识别模型提取，因此你不需要关注这些信息。

    重点关注以下方面：
    1. **政策背景**：论文涉及的具体政策文件（名称、年份、层级、核心内容）
    2. **现状数据**：描述当前状况的关键统计数据（如经济指标、投资金额、覆盖率等）
    3. **研究重要性**：本研究在理论和实践两个维度上的重要性和意义
    4. **核心文献**：论文引用的重要参考文献（作者、年份、核心观点）

    请仔细阅读论文的引言和背景章节，并以中文输出结构化的 JSON 格式。

    REQUIREMENTS:
    1. **Genre Classification**: 根据论文的研究方法和特征，分类为以下类型之一：
       - 'Case Study': 案例研究（单个案例的深入分析）
       - 'QCA': 定性比较分析（多案例条件组合分析）
       - 'Review': 文献综述（梳理现有研究进展）
       - 'Quantitative': 定量研究（有实证数据、统计检验）
       - 'Theoretical': 理论构建（提出新理论框架或模型）

    2. **Policy Context**: 列出论文中明确提及的所有政策文件，每个政策包含：
       - name: 政策文件名称（完整，如"党的二十大报告"）
       - year: 政策发布年份（如"2022"）
       - level: 政策层级（"Central"中央政府或"Local"地方政府）
       - content: 政策的核心内容或关键条款（简明扼要）

    3. **Status Data**: 提取描述当前状况的关键统计数据，每个数据项包含：
       - item: 数据项名称（如"GDP增长率"、"研发投入"）
       - value: 数据值（如"5.2%"、"1.2万亿"）
       - unit: 计量单位（如"亿元"、"万人"）
       - context: 数据的背景说明或解读（帮助理解数据的含义）

    4. **Research Significance**: 阐述本研究的重要性，从两个维度展开：
       - theoretical_significance: 理论意义——本研究在学术理论上的贡献和价值
       - practical_significance: 实践意义——本研究对现实问题或政策制定的指导作用

    5. **Key Literature**: 识别论文引用的重要参考文献，每条文献包含：
       - authors: 作者（完整姓名，如"张三、李四"）
       - year: 年份（如"2020"）
       - key_insights: 该文献的核心观点或对本研究的主要启发

    6. **Detailed Analysis**: 用约 300 字的中文进行综合阐述，包括：
       - 研究背景概述（1-2 句）
       - 政策环境和数据支撑（2-3 句）
       - 研究重要性（理论+实践各 2 句）
       - 文献基础的简要说明（1-2 句）

    Output JSON:
    {
        "policy_context": [
            {"name": "...", "year": "...", "level": "...", "content": "..."}
        ],
        "status_data": [
            {"item": "...", "value": "...", "unit": "...", "context": "..."}
        ],
        "research_significance": {
            "theoretical_significance": "...",
            "practical_significance": "..."
        },
        "key_literature": [
            {"authors": "...", "year": "...", "key_insights": "..."}
        ],
        "detailed_analysis": "约 300 字的中文综合阐述"
    }
    """
        
        return self._call_llm(prompt, text_segment, fallback_prompt="L1_Context (FALLBACK)", use_dynamic_prompt=(prompt is not None))

    def generate_markdown(self, data: dict, layer: str, basename: str, output_dir: str, metadata: dict = None):
        filename = f"{basename}_{layer}.md"
        path = os.path.join(output_dir, filename)
        
        # Prepare Frontmatter content
        frontmatter = {}
        
        # Inject common metadata if provided
        if metadata:
            frontmatter["title"] = metadata.get("title", basename)
            frontmatter["authors"] = metadata.get("authors", "")
            frontmatter["journal"] = metadata.get("journal", "")
            frontmatter["year"] = metadata.get("year", "")
            frontmatter["tags"] = ["SocialScience", metadata.get("genre", "Paper"), "LayerReport", layer]
        
        if layer == "L1_Context":
            # L1: 使用 policy_context, status_data, research_significance, key_literature
            if "policy_context" in data:
                frontmatter.update({
                    "key_policies": [p["name"] for p in data.get("policy_context", [])[:5]]
                })
            if "status_data" in data:
                frontmatter.update({
                    "status_summary": "; ".join([f"{d['item']}: {d['value']}" for d in data.get("status_data", [])[:3]])
                })
            if "research_significance" in data:
                rs = data.get("research_significance", {})
                significance_text = f"理论: {rs.get('theoretical_significance', '')}; 实践: {rs.get('practical_significance', '')}"
                frontmatter.update({"research_significance": significance_text})
            if "key_literature" in data:
                frontmatter.update({
                    "key_literature": [lit["authors"] for lit in data.get("key_literature", [])[:5]]
                })
        
        elif layer == "L2_Theory":
            frontmatter.update({
                "theories": [t["name"] for t in data.get("past_theories", [])[:5]],
                "key_constructs": [c["name"] for c in data.get("key_constructs", [])[:5]]
            })
        elif layer == "L3_Logic":
            mech = data.get("core_mechanism", {})
            frontmatter.update({
                "mechanism_type": mech.get("type"),
                "core_components": [c["phase_or_path"] for c in mech.get("components", [])[:5]]
            })
        elif layer == "L4_Value":
            frontmatter.update({
                "gaps": data.get("gaps", [])[:3],
                "contributions": data.get("contributions", [])[:3]
            })

        # Build Markdown
        lines = ["---"]
        for k, v in frontmatter.items():
            lines.append(f"{k}: {json.dumps(v, ensure_ascii=False)}")
        lines.append("---")
        lines.append(f"\n# {layer.replace('_', ': ')}")
        lines.append(f"\n## Detailed Analysis")
        lines.append(data.get("detailed_analysis", "No analysis provided."))
        
         # Add structured data sections
        lines.append("\n## Key Elements")
        
        if layer == "L1_Context":
            # L1: 使用新的字段结构
            lines.append("\n### Policy Context")
            for p in data.get("policy_context", []):
                lines.append(f"- **{p.get('name')}** ({p.get('year')}) [{p.get('level')}]")
                lines.append(f"  - {p.get('content')}")
            
            lines.append("\n### Status Data")
            for d in data.get("status_data", []):
                lines.append(f"- **{d.get('item')}**: {d.get('value')} {d.get('unit', '')}")
                if d.get('context'):
                    lines.append(f"  - Context: {d.get('context')}")
            
            if "research_significance" in data:
                rs = data.get("research_significance", {})
                lines.append("\n### Research Significance")
                lines.append(f"- **Theoretical Significance**: {rs.get('theoretical_significance', '未说明')}")
                lines.append(f"- **Practical Significance**: {rs.get('practical_significance', '未说明')}")
            
            if "key_literature" in data:
                lines.append("\n### Key Literature")
                for lit in data.get("key_literature", []):
                    lines.append(f"- **{lit.get('authors')}** ({lit.get('year')}): {lit.get('key_insights')}")

        elif layer == "L2_Theory":
            lines.append("\n### Past Theories")
            for t in data.get("past_theories", []):
                lines.append(f"- **{t.get('name')}**: {t.get('summary')}")
            
            lines.append("\n### Key Constructs")
            for c in data.get("key_constructs", []):
                lines.append(f"- **{c.get('name')}**: {c.get('definition')}")
            
            lines.append("\n### Relationships")
            for r in data.get("relationships", []):
                lines.append(f"- **{r.get('from')}** -> **{r.get('to')}**: {r.get('mechanism')}")
            
            lines.append("\n### Framework Description")
            lines.append(data.get("framework_desc", ""))

        elif layer == "L3_Logic":
            mech = data.get("core_mechanism", {})
            lines.append(f"\n### Mechanism Type: {mech.get('type')}")
            for c in mech.get("components", []):
                lines.append(f"- **{c.get('phase_or_path')}**")
                lines.append(f"  - Description: {c.get('description')}")
                lines.append(f"  - Evidence: {c.get('evidence')}")

        elif layer == "L4_Value":
            lines.append("\n### Gaps")
            for g in data.get("gaps", []):
                lines.append(f"- {g}")
            
            lines.append("\n### Contributions")
            for c in data.get("contributions", []):
                lines.append(f"- {c}")
            
            lines.append("\n### Implications")
            for i in data.get("implications", []):
                lines.append(f"- {i}")

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path

    def generate_full_report(self, all_data: dict, basename: str, output_dir: str):
        l1 = all_data.get("L1", {})
        l2 = all_data.get("L2", {})
        l3 = all_data.get("L3", {})
        l4 = all_data.get("L4", {})
        
        lines = ["---"]
        lines.append(f"title: {basename}")
        lines.append(f"authors: {l1.get('policy_context', [{}])[0].get('name', '') if l1.get('policy_context') else ''}")
        lines.append(f"journal: {l1.get('status_data', [{}])[0].get('item', '') if l1.get('status_data') else ''}")
        lines.append(f"year: {l1.get('key_literature', [{}])[0].get('year', '') if l1.get('key_literature') else ''}")
        lines.append(f"tags: #SocialScience #{l1.get('research_significance', {}).get('theoretical_significance', '')} #DeepReading")
        lines.append(f"date: {datetime.now().strftime('%Y-%m-%d')}")
        lines.append("---")
        
        lines.append(f"\n# 深度阅读报告：{basename}\n")
        
        lines.append("## 1. 基础情报")
        lines.append(l1.get("detailed_analysis", ""))
        
        if l1.get("policy_context"):
            lines.append("\n### 关键政策")
            for p in l1.get("policy_context", [])[:5]:
                lines.append(f"- **{p.get('name')}** ({p.get('year')}) [{p.get('level')}]")
                lines.append(f"  - {p.get('content')}")
        
        if l1.get("status_data"):
            lines.append("\n### 现状数据")
            for d in l1.get("status_data", [])[:3]:
                lines.append(f"- **{d.get('item')}**: {d.get('value')} {d.get('unit', '')}")
                if d.get('context'):
                    lines.append(f"  - Context: {d.get('context')}")
        
        if l1.get("research_significance"):
            lines.append("\n## 2. 研究重要性")
            rs = l1.get("research_significance", {})
            lines.append(f"**理论意义**: {rs.get('theoretical_significance', '')}")
            lines.append(f"**实践意义**: {rs.get('practical_significance', '')}")
        
        if l1.get("key_literature"):
            lines.append("\n### 核心文献")
            for lit in l1.get("key_literature", [])[:5]:
                lines.append(f"- **{lit.get('authors')}** ({lit.get('year')}): {lit.get('key_insights', '')}")
        
        lines.append("\n## 3. 核心逻辑")
        lines.append(l2.get("detailed_analysis", ""))
        
        lines.append(f"\n### {l3.get('core_mechanism', {}).get('type', 'Mechanism')}")
        for c in l3.get("core_mechanism", {}).get("components", []):
            lines.append(f"- **{c.get('phase_or_path')}**: {c.get('description')}")
            if c.get("evidence"):
                lines.append(f"  - Evidence: {c.get('evidence')}")
        
        lines.append("\n## 4. 价值升华")
        lines.append(l4.get("detailed_analysis", ""))
        
        if l4.get("gaps"):
            lines.append("\n### 研究缺口")
            for g in l4.get("gaps", [])[:3]:
                lines.append(f"- {g}")
        
        if l4.get("contributions"):
            lines.append("\n### 学术贡献")
            for c in l4.get("contributions", [])[:3]:
                lines.append(f"- {c}")
        
        if l4.get("implications"):
            lines.append("\n### 实践启示")
            for i in l4.get("implications", []):
                lines.append(f"- {i}")
        
        path = os.path.join(output_dir, f"{basename}_Full_Report.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return path

    def flatten_for_excel(self, all_data_list: list) -> pd.DataFrame:
        rows = []
        for item in all_data_list:
            basename = item["basename"]
            l1 = item["data"].get("L1", {})
            l2 = item["data"].get("L2", {})
            l3 = item["data"].get("L3", {})
            l4 = item["data"].get("L4", {})
            
            row = {
                "Filename": basename,
                "Title": l1.get("metadata", {}).get("title"),
                "Genre": l1.get("metadata", {}).get("genre"),
                "Key Policies": "; ".join([p["name"] for p in l1.get("policy_context", [])]),
                "Key Constructs": "; ".join([c["name"] for c in l2.get("key_constructs", [])]),
                "Core Mechanism Type": l3.get("core_mechanism", {}).get("type"),
                "Theoretical Contributions": "; ".join(l4.get("contributions", [])),
                "Practical Implications": "; ".join(l4.get("implications", []))
            }
            rows.append(row)
        return pd.DataFrame(rows)

def load_segmented_md(path: str) -> dict:
    """
    Parse a markdown file into sections.
    Supports raw extraction output (# and ## headers), traditional segmented format,
    and Smart Router format (L1-L4).
    Strips YAML frontmatter before parsing.
    Falls back to {"Full Text": content} if no sections found.
    """
    import re as _re
    sections = {}
    current_section = None
    buffer = []

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # Strip YAML frontmatter
    content = _re.sub(r'^---\n.*?\n---\n', '', content, flags=_re.DOTALL)

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
    从 Smart Router QUAL 格式中提取 L1-L4 层级的实际文本内容。
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
            # Extract text from ```text ... ``` code blocks
            import re
            text_blocks = re.findall(r'```text\s*\n(.*?)\n```', content, re.DOTALL)
            if text_blocks:
                extracted[layer_key] = "\n\n".join(text_blocks)
            else:
                extracted[layer_key] = content
    
    logger.info(f"Extracted {len(extracted)} layers from Smart Router QUAL format")
    return extracted

def get_combined_text(sections: dict, keys: list) -> str:
    """Combine text from specific sections based on keywords."""
    text = ""
    for k, v in sections.items():
        if any(key.lower() in k.lower() for key in keys):
            text += v + "\n"
    return text if text else "".join(sections.values())[:30000] # Fallback

def main():
    parser = argparse.ArgumentParser(description="Social Science 4-Layer Analyzer")
    parser.add_argument("segmented_dir", help="Directory containing Segmented MD files")
    parser.add_argument("--out_dir", default="social_science_results_v2", help="Output directory")
    parser.add_argument("--filter", nargs="+", help="Keywords to filter filenames")
    args = parser.parse_args()

    analyzer = SocialScienceAnalyzer()
    os.makedirs(args.out_dir, exist_ok=True)
    
    # Process target files (accept extraction or segmented outputs)
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
        
        # Check if Smart Router QUAL format (already extracted L1-L4)
        if "L1_Context" in sections:
            logger.info("Using Smart Router QUAL format - L1-L4 already extracted")
            text_l1 = sections.get("L1_Context", "")
            text_l2 = sections.get("L2_Theory", "")
            text_l3 = sections.get("L3_Logic", "")
            text_l4 = sections.get("L4_Value", "")
        else:
            # Traditional format: Define context for each layer using keyword matching
            text_l1 = get_combined_text(sections, ["abstract", "introduction", "background", "摘要", "引言", "背景", "绪论", "问题提出"])
            
            # Fallback for L1 if empty (common in papers without explicit Introduction header)
            if len(text_l1) < 200:
                keys = list(sections.keys())
                if keys:
                    text_l1 = sections[keys[0]]
                    if len(keys) > 1:
                        text_l1 += "\n" + sections[keys[1]]
            
            text_l2 = get_combined_text(sections, ["literature", "theory", "theoretical", "文献", "综述", "理论", "基础", "研究现状"])
            text_l3 = get_combined_text(sections, ["method", "result", "finding", "case", "analysis", "方法", "设计", "案例", "结果", "分析", "实证", "模型", "路径", "机制"])
            text_l4 = get_combined_text(sections, ["discussion", "conclusion", "implication", "讨论", "结论", "启示", "展望", "建议", "结语"])
        
        # Execute 4 Layers
        l1_res = analyzer.analyze_l1_context(text_l1)
        
        # L1 不再返回 genre，使用默认值或从文本推断
        genre = "Case Study"  # 默认体裁
        
        l2_res = analyzer.analyze_l2_theory(text_l2)
        l3_res = analyzer.analyze_l3_logic(text_l3, genre=genre)
        l4_res = analyzer.analyze_l4_value(text_l4)
        
        paper_data = {"L1": l1_res, "L2": l2_res, "L3": l3_res, "L4": l4_res}
        
        # Generate Outputs
        paper_out_dir = os.path.join(args.out_dir, basename)
        os.makedirs(paper_out_dir, exist_ok=True)
        
        # Extract common metadata for injection
        common_meta = l1_res.get("metadata", {})
        
        analyzer.generate_markdown(l1_res, "L1_Context", basename, paper_out_dir, metadata=common_meta)
        analyzer.generate_markdown(l2_res, "L2_Theory", basename, paper_out_dir, metadata=common_meta)
        analyzer.generate_markdown(l3_res, "L3_Logic", basename, paper_out_dir, metadata=common_meta)
        analyzer.generate_markdown(l4_res, "L4_Value", basename, paper_out_dir, metadata=common_meta)
        analyzer.generate_full_report(paper_data, basename, paper_out_dir)
        
        all_results.append({"basename": basename, "data": paper_data})

    # Generate Excel
    if all_results:
        df = analyzer.flatten_for_excel(all_results)
        df.to_excel(os.path.join(args.out_dir, "Social_Science_Analysis_4Layer.xlsx"), index=False)
        logger.info("Batch Analysis Complete.")

if __name__ == "__main__":
    main()
