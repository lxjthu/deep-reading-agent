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

    def _call_llm(self, system_prompt: str, user_content: str) -> dict:
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
            return json_repair.repair_json(content, return_objects=True)
        except Exception as e:
            logger.error(f"LLM Call Error: {e}")
            return {}

    def analyze_l1_context(self, text_segment: str) -> dict:
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
    "detailed_analysis": "A 300-word detailed narrative of the context and background in Chinese."
}
"""
        return self._call_llm(prompt, text_segment)

    def analyze_l2_theory(self, text_segment: str) -> dict:
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
    "detailed_analysis": "A 400-word deep dive into the theoretical logic and construct definitions in Chinese."
}
"""
        return self._call_llm(prompt, text_segment)

    def analyze_l3_logic(self, text_segment: str, genre: str) -> dict:
        prompt = f"""
You are a Social Science Logic Analyst. Extract the Core Mechanism or Path.
The paper genre is: {genre}.
Focus on "Methodology", "Case Description", and "Results" sections.
IMPORTANT: ALL OUTPUT MUST BE IN CHINESE (SIMPLIFIED).

REQUIREMENTS based on genre:
- If **Case Study**: Extract the "Process Model" (Phases, Events, Strategies).
- If **QCA/Quant**: Extract "Causal Paths/Configurations" or "Hypothesis Results".
- If **Review**: Extract the "Integrated Framework" or "Evolution Map".

Output JSON:
{{
"core_mechanism": {{
    "type": "{genre} Logic",
    "components": [
        {{"phase_or_path": "...", "description": "...", "evidence": "..."}}
    ]
}},
"detailed_analysis": "A 500-word detailed narrative of the core mechanism/findings in Chinese. Be very specific."
}}
"""
        return self._call_llm(prompt, text_segment)

    def analyze_l4_value(self, text_segment: str) -> dict:
        prompt = """
You are a Social Science Value Analyst. Extract Gaps, Contributions, and Implications.
Focus on "Discussion" and "Conclusion" sections.
IMPORTANT: ALL OUTPUT MUST BE IN CHINESE (SIMPLIFIED).

REQUIREMENTS:
1. **Gaps**: Specific limitations of previous studies mentioned.
2. **Contributions**: How this paper advances theory/practice.
3. **Implications**: Actionable advice for policymakers/practitioners.

Output JSON:
{
    "gaps": ["..."],
    "contributions": ["..."],
    "implications": ["..."],
    "detailed_analysis": "A 300-word summary of the paper's value proposition in Chinese."
}
"""
        return self._call_llm(prompt, text_segment)

    def generate_markdown(self, data: dict, layer: str, basename: str, output_dir: str):
        filename = f"{basename}_{layer}.md"
        path = os.path.join(output_dir, filename)
        
        # Prepare Frontmatter content
        frontmatter = {}
        if layer == "L1_Context":
            frontmatter = {
                "genre": data.get("metadata", {}).get("genre"),
                "key_policies": [p["name"] for p in data.get("policy_context", [])[:5]],
                "status_summary": "; ".join([f"{d['item']}: {d['value']}" for d in data.get("status_data", [])[:3]])
            }
        elif layer == "L2_Theory":
            frontmatter = {
                "theories": [t["name"] for t in data.get("past_theories", [])[:5]],
                "key_constructs": [c["name"] for c in data.get("key_constructs", [])[:5]]
            }
        elif layer == "L3_Logic":
            mech = data.get("core_mechanism", {})
            frontmatter = {
                "mechanism_type": mech.get("type"),
                "core_components": [c["phase_or_path"] for c in mech.get("components", [])[:5]]
            }
        elif layer == "L4_Value":
            frontmatter = {
                "gaps": data.get("gaps", [])[:3],
                "contributions": data.get("contributions", [])[:3]
            }

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
            meta = data.get("metadata", {})
            lines.append("\n### Metadata")
            for k, v in meta.items():
                lines.append(f"- **{k}**: {v}")
            
            lines.append("\n### Policy Context")
            for p in data.get("policy_context", []):
                lines.append(f"- **{p.get('name')}** ({p.get('year')}) [{p.get('level')}]")
                lines.append(f"  - {p.get('content')}")
            
            lines.append("\n### Status Data")
            for d in data.get("status_data", []):
                lines.append(f"- **{d.get('item')}**: {d.get('value')} {d.get('unit', '')}")
                if d.get('context'):
                    lines.append(f"  - Context: {d.get('context')}")

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
        
        meta = l1.get("metadata", {})
        
        lines = ["---"]
        lines.append(f"title: {meta.get('title', basename)}")
        lines.append(f"authors: {meta.get('authors', '')}")
        lines.append(f"tags: #SocialScience #{meta.get('genre', 'Paper')} #DeepReading")
        lines.append(f"date: {datetime.now().strftime('%Y-%m-%d')}")
        lines.append("---")
        
        lines.append(f"\n# 深度阅读报告：{meta.get('title', basename)}\n")
        
        lines.append("## 1. 基础情报 (Context & Metadata)")
        lines.append(l1.get("detailed_analysis", ""))
        lines.append("\n### 关键政策")
        for p in l1.get("policy_context", []):
            lines.append(f"- **{p.get('name')}** ({p.get('year')}): {p.get('content')}")
        
        lines.append("\n## 2. 理论探讨 (Theoretical Foundation)")
        lines.append(l2.get("detailed_analysis", ""))
        lines.append("\n### 关键构念")
        for c in l2.get("key_constructs", []):
            lines.append(f"- **{c.get('name')}**: {c.get('definition')}")
            
        lines.append("\n## 3. 核心逻辑 (Logic & Mechanism)")
        lines.append(l3.get("detailed_analysis", ""))
        lines.append(f"\n### {l3.get('core_mechanism', {}).get('type', 'Mechanism')}")
        for c in l3.get("core_mechanism", {}).get("components", []):
            lines.append(f"- **{c.get('phase_or_path')}**: {c.get('description')}")
            
        lines.append("\n## 4. 价值升华 (Value & Implications)")
        lines.append(l4.get("detailed_analysis", ""))
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
    """Simple parser to split segmented MD into sections."""
    sections = {}
    current_section = "General"
    buffer = []
    
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith("## "):
                if buffer:
                    sections[current_section] = "".join(buffer)
                current_section = line.strip().replace("## ", "")
                buffer = []
            else:
                buffer.append(line)
        if buffer:
            sections[current_section] = "".join(buffer)
    return sections

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
    
    # Process only target files (simulating the specific task)
    all_files = [f for f in os.listdir(args.segmented_dir) if f.endswith("_segmented.md")]
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
        basename = filename.replace("_segmented.md", "")
        file_path = os.path.join(args.segmented_dir, filename)
        logger.info(f"Processing {basename}...")
        
        sections = load_segmented_md(file_path)
        
        # Define context for each layer
        # Heuristics for section matching (English + Chinese)
        text_l1 = get_combined_text(sections, ["abstract", "introduction", "background", "摘要", "引言", "背景", "绪论", "问题提出"])
        
        # Fallback for L1 if empty (common in papers without explicit Introduction header)
        if len(text_l1) < 200:
            # Use the first 1-2 sections as context
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
        genre = l1_res.get("metadata", {}).get("genre", "Case Study")
        
        l2_res = analyzer.analyze_l2_theory(text_l2)
        l3_res = analyzer.analyze_l3_logic(text_l3, genre)
        l4_res = analyzer.analyze_l4_value(text_l4)
        
        paper_data = {"L1": l1_res, "L2": l2_res, "L3": l3_res, "L4": l4_res}
        
        # Generate Outputs
        paper_out_dir = os.path.join(args.out_dir, basename)
        os.makedirs(paper_out_dir, exist_ok=True)
        
        analyzer.generate_markdown(l1_res, "L1_Context", basename, paper_out_dir)
        analyzer.generate_markdown(l2_res, "L2_Theory", basename, paper_out_dir)
        analyzer.generate_markdown(l3_res, "L3_Logic", basename, paper_out_dir)
        analyzer.generate_markdown(l4_res, "L4_Value", basename, paper_out_dir)
        analyzer.generate_full_report(paper_data, basename, paper_out_dir)
        
        all_results.append({"basename": basename, "data": paper_data})

    # Generate Excel
    if all_results:
        df = analyzer.flatten_for_excel(all_results)
        df.to_excel(os.path.join(args.out_dir, "Social_Science_Analysis_4Layer.xlsx"), index=False)
        logger.info("Batch Analysis Complete.")

if __name__ == "__main__":
    main()
