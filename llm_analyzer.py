import os
import json
import logging
import json_repair
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class LLMAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o")
        
        if not self.api_key:
            self.logger.warning("OPENAI_API_KEY not found in environment variables. LLM features will fail.")
            self.client = None
        else:
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def analyze(self, text, filename=""):
        """
        Sends the text to LLM for structured analysis.
        """
        if not self.client:
            return {"error": "No API Key configured"}

        if len(text) > 150000:
            text_input = text[:100000] + "\n\n...[Middle section omitted]...\n\n" + text[-50000:]
        else:
            text_input = text

        prompt = f"""
        You are an expert in Econometrics and Academic Research (Acemoglu Level).
        Analyze the following academic paper content (extracted from PDF) and extract structured information for a **Meta-Analysis Table**.
        
        Paper Filename: {filename}
        
        # CRITICAL INSTRUCTION
        1. Extract information in **Simplified Chinese**.
        2. Be **CONCISE**. The output is for a table, so keep descriptions short (1-2 sentences max per field).
        3. Focus on "Acemoglu-level" precision: Identification Strategy, Mechanisms, Data Quality.
        
        # Extraction Fields (JSON Keys)
        
        1. **Basic Info**:
           - title: Paper title
           - authors: Authors list
           - journal: Journal name
           - year: Publication year
           
        2. **Big Picture** (Part 1):
           - theme: Research Theme (研究主题) - 1 sentence.
           - problem: Research Question (科学问题) - What specific problem is solved?
           - contribution: Contribution (核心贡献) - Theory or Practice.
           
        3. **Theory & Hypotheses** (Part 2):
           - theory_base: Theoretical Foundation (理论基础) - e.g., "Human Capital Theory".
           - hypothesis: Core Hypothesis (核心假说).
           
        4. **Data** (Part 3):
           - data_source: Data Source (数据来源) - e.g., "CHFS 2019", "World Bank".
           - sample_info: Sample Characteristics (样本特征) - e.g., "3000 rural households in China".
           
        5. **Measurement** (Part 4):
           - dep_var: Dependent Variable Y (被解释变量) - Name & Measure.
           - indep_var: Independent Variable X (核心解释变量) - Name & Measure.
           - controls: Control Variables (控制变量) - Brief list.
           
        6. **Identification** (Part 5):
           - model: Econometric Model (计量模型) - e.g., "Fixed Effects", "DID".
           - strategy: Identification Strategy (识别策略) - How endogeneity is handled?
           - iv_mechanism: IV or Mechanism (工具/机制变量).
           
        7. **Results & Critique** (Part 6 & 7):
           - findings: Core Findings (主要结论) - 1-2 key results.
           - weakness: Weakness/Critique (潜在不足/致命伤) - e.g., "Weak IV", "External validity".
           
        8. **Stata Code**:
           - stata_code: Generate expert-level Stata code (in English) for the main regression.
           
        # Output Format
        Return ONLY valid JSON.
        {{
            "basic": {{ "title": "...", "authors": "...", "journal": "...", "year": "..." }},
            "overview": {{ "theme": "...", "problem": "...", "contribution": "..." }},
            "theory": {{ "theory_base": "...", "hypothesis": "..." }},
            "data": {{ "data_source": "...", "sample_info": "..." }},
            "measurement": {{ "dep_var": "...", "indep_var": "...", "controls": "..." }},
            "identification": {{ "model": "...", "strategy": "...", "iv_mechanism": "..." }},
            "results": {{ "findings": "...", "weakness": "..." }},
            "stata_code": "..."
        }}
        
        # Paper Content
        {text_input}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a precise academic research assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            try:
                return json_repair.repair_json(content, return_objects=True)
            except Exception as json_err:
                self.logger.error(f"JSON Parsing failed: {json_err}")
                return {"error": f"JSON Parse Error: {str(json_err)}"}
            
        except Exception as e:
            self.logger.error(f"LLM Analysis failed: {e}")
            return {"error": str(e)}

    def generate_markdown_report(self, data, output_path):
        """
        Converts the JSON analysis into a readable Markdown Table report.
        """
        if "error" in data:
            return
            
        b = data.get('basic', {})
        o = data.get('overview', {})
        t = data.get('theory', {})
        d = data.get('data', {})
        m = data.get('measurement', {})
        i = data.get('identification', {})
        r = data.get('results', {})
        
        md = f"""# {b.get('title', 'Paper Analysis')}

**Authors**: {b.get('authors', 'N/A')} | **Journal**: {b.get('journal', 'N/A')} | **Year**: {b.get('year', 'N/A')}

## 核心要素提取表 (Deep Reading Extraction)

| 维度 | 要素 | 内容提取 |
| :--- | :--- | :--- |
| **1. 全景扫描** | **研究主题** | {o.get('theme', '')} |
| | **科学问题** | {o.get('problem', '')} |
| | **核心贡献** | {o.get('contribution', '')} |
| **2. 理论基础** | **理论框架** | {t.get('theory_base', '')} |
| | **核心假说** | {t.get('hypothesis', '')} |
| **3. 数据** | **数据来源** | {d.get('data_source', '')} |
| | **样本特征** | {d.get('sample_info', '')} |
| **4. 变量** | **被解释变量 (Y)** | {m.get('dep_var', '')} |
| | **核心解释变量 (X)** | {m.get('indep_var', '')} |
| | **控制变量** | {m.get('controls', '')} |
| **5. 识别策略** | **计量模型** | {i.get('model', '')} |
| | **识别挑战与策略** | {i.get('strategy', '')} |
| | **工具/机制变量** | {i.get('iv_mechanism', '')} |
| **6. 结果与评价** | **主要发现** | {r.get('findings', '')} |
| | **研究不足** | {r.get('weakness', '')} |

## Stata 代码建议

```stata
{data.get('stata_code', '')}
```
"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md)
