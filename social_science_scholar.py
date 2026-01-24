import os
import sys
import glob
import json
import logging
import argparse
import pandas as pd
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
import json_repair

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

class SocialScienceScholar:
    def __init__(self, model_name="deepseek-chat", base_url="https://api.deepseek.com"):
        self.api_key = os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DEEPSEEK_API_KEY not found in environment")
        self.client = OpenAI(api_key=self.api_key, base_url=base_url)
        self.model_name = model_name

    def analyze_paper(self, raw_md_content: str, filename: str) -> dict:
        """
        Analyzes the paper using LLM to extract the 5 key dimensions + metadata.
        """
        logger.info(f"Analyzing {filename} with {self.model_name}...")
        
        system_prompt = """You are a distinguished scholar in Management and Sociology. 
Your task is to conduct a "Deep Reading" of an academic paper and extract structured intelligence.
You must adopt a critical, insightful, and context-aware perspective.

You need to extract information into a JSON object with the following structure:

{
    "metadata": {
        "title": "Paper Title",
        "authors": "Author Names",
        "type": "Case Study / Review / QCA / Quantitative / Theoretical",
        "year": "Year",
        "journal": "Journal Name"
    },
    "significance": {
        "theoretical": "Why is this important theoretically?",
        "practical": "Why is this important practically? What real-world problem does it solve?"
    },
    "context": {
        "policy_background": [
            {"name": "Policy Name", "details": "Year, Level, Key content mentioned"}
        ],
        "status_data": [
            {"item": "Key Metric/Fact", "value": "Value/Description"}
        ]
    },
    "literature": {
        "evolution": "Brief summary of how the field evolved",
        "debates": "Key debates or conflicts mentioned",
        "gaps": "Specific gaps this paper aims to fill"
    },
    "core_content": {
        "theory_lens": "Theoretical framework used",
        "methodology": "Method details (Case selection, Data source, etc.)",
        "mechanism_or_findings": "The core 'How' or 'What'. For Case: Process Model. For QCA: Configurations. For Review: Framework."
    },
    "insights": {
        "theoretical_contribution": "Key contribution to theory",
        "counter_intuitive": "Any surprising or counter-intuitive findings?",
        "practical_implications": "Actionable advice for practitioners/policymakers"
    },
    "summary": "A 200-word executive summary of the paper."
}
"""

        user_prompt = f"""
Here is the content of the paper "{filename}":

{raw_md_content[:60000]} 

---
Please analyze it and provide the JSON output. 
Focus on:
1. **Significance**: Why it matters?
2. **Policy & Data**: Specific policy names and status data are crucial.
3. **Literature**: The flow and the gap.
4. **Core Insights**: The mechanism/pathways.
"""
        
        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                max_tokens=4000
            )
            
            content = response.choices[0].message.content
            data = json_repair.repair_json(content, return_objects=True)
            return data

        except Exception as e:
            logger.error(f"Error analyzing paper: {e}")
            return {}

    def generate_markdown_report(self, data: dict, output_path: str):
        """Generates a detailed Markdown deep reading report."""
        
        md = []
        meta = data.get("metadata", {})
        sig = data.get("significance", {})
        ctx = data.get("context", {})
        lit = data.get("literature", {})
        core = data.get("core_content", {})
        ins = data.get("insights", {})
        
        # Frontmatter
        md.append("---")
        md.append(f"title: {meta.get('title', 'Untitled')}")
        md.append(f"authors: {meta.get('authors', '')}")
        md.append(f"tags: #DeepReading #{meta.get('type', 'Paper').replace(' ', '')} #SocialScience")
        md.append(f"date: {datetime.now().strftime('%Y-%m-%d')}")
        md.append("---")
        
        md.append(f"# 深度阅读笔记：{meta.get('title')}\n")
        
        md.append("## 0. 摘要 (Executive Summary)")
        md.append(f"{data.get('summary', 'No summary available.')}\n")
        
        md.append("## 1. 选题价值 (Significance)")
        md.append(f"### 理论重要性\n{sig.get('theoretical', '')}\n")
        md.append(f"### 实践重要性\n{sig.get('practical', '')}\n")
        
        md.append("## 2. 情境全景 (Context & Background)")
        md.append("### 关键政策背景")
        if ctx.get("policy_background"):
            for p in ctx["policy_background"]:
                md.append(f"- **{p.get('name', 'Policy')}**: {p.get('details', '')}")
        else:
            md.append("- 未提取到具体政策")
        md.append("\n### 关键现状数据")
        if ctx.get("status_data"):
            for d in ctx["status_data"]:
                md.append(f"- **{d.get('item', 'Item')}**: {d.get('value', '')}")
        else:
            md.append("- 未提取到具体数据")
        md.append("")
        
        md.append("## 3. 文献源流 (Literature Stream)")
        md.append(f"- **演进脉络**: {lit.get('evolution', '')}")
        md.append(f"- **主要争论**: {lit.get('debates', '')}")
        md.append(f"- **研究缺口 (Gap)**: {lit.get('gaps', '')}\n")
        
        md.append("## 4. 研究内核 (Core Content)")
        md.append(f"- **理论视角**: {core.get('theory_lens', '')}")
        md.append(f"- **方法论**: {core.get('methodology', '')}")
        md.append(f"### 核心机制/发现\n{core.get('mechanism_or_findings', '')}\n")
        
        md.append("## 5. 洞见与启示 (Insights)")
        md.append(f"### 理论贡献\n{ins.get('theoretical_contribution', '')}\n")
        md.append(f"### 反直觉/新颖发现\n{ins.get('counter_intuitive', '')}\n")
        md.append(f"### 实践启示\n{ins.get('practical_implications', '')}\n")
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(md))
        logger.info(f"Markdown report saved to {output_path}")

    def flatten_for_excel(self, data_list: list) -> pd.DataFrame:
        """Flattens the nested JSON list into a DataFrame."""
        rows = []
        for d in data_list:
            meta = d.get("metadata", {})
            sig = d.get("significance", {})
            lit = d.get("literature", {})
            core = d.get("core_content", {})
            ins = d.get("insights", {})
            
            # Helper to join list of dicts
            def join_list(lst, key_field, val_field):
                if not lst: return ""
                return "; ".join([f"{x.get(key_field)}: {x.get(val_field)}" for x in lst])

            row = {
                "Title": meta.get("title"),
                "Authors": meta.get("authors"),
                "Type": meta.get("type"),
                "Year": meta.get("year"),
                "Journal": meta.get("journal"),
                "Theoretical Significance": sig.get("theoretical"),
                "Practical Significance": sig.get("practical"),
                "Policies": join_list(d.get("context", {}).get("policy_background", []), "name", "details"),
                "Status Data": join_list(d.get("context", {}).get("status_data", []), "item", "value"),
                "Literature Gap": lit.get("gaps"),
                "Theory Lens": core.get("theory_lens"),
                "Methodology": core.get("methodology"),
                "Core Mechanism/Findings": core.get("mechanism_or_findings"),
                "Theoretical Contribution": ins.get("theoretical_contribution"),
                "Practical Implications": ins.get("practical_implications")
            }
            rows.append(row)
        return pd.DataFrame(rows)

def main():
    parser = argparse.ArgumentParser(description="Social Science Scholar - Deep Reading Skill")
    parser.add_argument("pdf_dir", help="Directory containing PDF files")
    parser.add_argument("raw_md_dir", help="Directory containing Raw MD files (or where to save them)")
    parser.add_argument("--out_dir", default="social_science_results", help="Output directory for Excel and MD")
    args = parser.parse_args()

    scholar = SocialScienceScholar()
    
    os.makedirs(args.out_dir, exist_ok=True)
    
    # Target specific files as requested by user (hardcoded filter for safety/precision based on user request)
    target_files = [
        "“含绿量”如何赋能“含金量”_生态产品价值转化的理论逻辑与实现机制——基于浙江省L市政策“组合拳”的考察分析",
        "中国生态产品价值实现研究进展与展望",
        "组态视角下生态产品价值实现的路径研究——基于30个省市的模糊集定性比较分析"
    ]
    
    results = []
    
    # Find matching raw MD files
    for basename in target_files:
        # Try to find the file in raw_md_dir (fuzzy match or exact)
        pattern = os.path.join(args.raw_md_dir, f"*{basename}*_raw.md")
        files = glob.glob(pattern)
        
        if not files:
            logger.warning(f"Could not find raw MD for {basename}")
            continue
            
        file_path = files[0] # Take the first match
        logger.info(f"Processing {file_path}...")
        
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        analysis = scholar.analyze_paper(content, basename)
        results.append(analysis)
        
        # Generate MD Report
        md_name = f"{basename}_deep_reading.md"
        scholar.generate_markdown_report(analysis, os.path.join(args.out_dir, md_name))

    # Generate Excel
    if results:
        df = scholar.flatten_for_excel(results)
        excel_path = os.path.join(args.out_dir, "Social_Science_Literature_Analysis.xlsx")
        df.to_excel(excel_path, index=False)
        logger.info(f"Excel summary saved to {excel_path}")
    else:
        logger.warning("No results to save.")

if __name__ == "__main__":
    main()
