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

    def analyze(self, text, filename="", mode="QUANT"):
        """
        Sends the text to LLM for structured analysis.
        Mode: "QUANT" (default) or "QUAL".
        """
        if not self.client:
            return {"error": "No API Key configured"}

        if len(text) > 150000:
            text_input = text[:100000] + "\n\n...[Middle section omitted]...\n\n" + text[-50000:]
        else:
            text_input = text

        if mode == "QUAL":
            prompt = self._get_qual_prompt(text_input, filename)
        else:
            prompt = self._get_quant_prompt(text_input, filename)

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
                result = json_repair.repair_json(content, return_objects=True)
                result["mode"] = mode # Tag the result
                return result
            except Exception as json_err:
                self.logger.error(f"JSON Parsing failed: {json_err}")
                return {"error": f"JSON Parse Error: {str(json_err)}"}
            
        except Exception as e:
            self.logger.error(f"LLM Analysis failed: {e}")
            return {"error": str(e)}

    def _get_quant_prompt(self, text_input, filename):
        return f"""
        You are an expert in Econometrics and Academic Research (Acemoglu Level).
        Analyze the following QUANTITATIVE academic paper and extract structured information.
        
        Paper Filename: {filename}
        
        # CRITICAL INSTRUCTION
        1. Extract information in **Simplified Chinese**.
        2. Be **CONCISE** (1-2 sentences max per field).
        
        # Extraction Fields (JSON Keys)
        
        1. **Basic Info**: title, authors, journal, year
        2. **Big Picture**: theme (研究主题), problem (科学问题), contribution (核心贡献)
        3. **Theory**: theory_base (理论基础), hypothesis (核心假说)
        4. **Data**: data_source (数据来源), sample_info (样本特征)
        5. **Measurement**: dep_var (被解释变量), indep_var (核心解释变量), controls (控制变量)
        6. **Identification**: model (计量模型), strategy (识别策略), iv_mechanism (工具/机制变量)
        7. **Results**: findings (主要结论), weakness (潜在不足)
        8. **Stata Code**: stata_code (Expert level code in English)
           
        # Output JSON Format
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

    def _get_qual_prompt(self, text_input, filename):
        return f"""
        You are an expert in Qualitative Social Science Research (Case Study/Grounded Theory/QCA).
        Analyze the following QUALITATIVE academic paper and extract structured information, MAPPING it to standard schema keys where possible.
        
        Paper Filename: {filename}
        
        # CRITICAL INSTRUCTION
        1. Extract information in **Simplified Chinese**.
        2. Be **CONCISE**.
        
        # Mapping Instructions (Qual -> Standard Schema)
        - **Theory Base**: Core Constructs & Definitions (核心构念).
        - **Hypothesis**: Theoretical Framework/Propositions (理论框架/命题).
        - **Data Source**: Case Selection/Interview Data (案例选择/访谈资料).
        - **Sample Info**: Case Background (案例背景).
        - **Dep Var**: Outcome/Phenomenon (结果/现象).
        - **Indep Var**: Core Condition/Driver (核心条件/驱动因素).
        - **Model**: Analysis Method (e.g., QCA, Grounded Theory) (分析方法).
        - **Strategy**: Process Model/Configurational Path (过程模型/组态路径).
        
        # Extraction Fields (JSON Keys)
        
        1. **Basic Info**: title, authors, journal, year
        2. **Big Picture**: theme, problem, contribution
        3. **Theory**: theory_base (Constructs), hypothesis (Framework)
        4. **Data**: data_source (Cases), sample_info (Background)
        5. **Measurement**: dep_var (Outcome), indep_var (Conditions), controls (Context)
        6. **Identification**: model (Method), strategy (Process/Path), iv_mechanism (Mechanism)
        7. **Results**: findings (Key Insights), weakness (Limitations)
        8. **Stata Code**: Return "N/A (Qualitative Paper)"
           
        # Output JSON Format (Keep same structure as Quant for compatibility)
        {{
            "basic": {{ "title": "...", "authors": "...", "journal": "...", "year": "..." }},
            "overview": {{ "theme": "...", "problem": "...", "contribution": "..." }},
            "theory": {{ "theory_base": "...", "hypothesis": "..." }},
            "data": {{ "data_source": "...", "sample_info": "..." }},
            "measurement": {{ "dep_var": "...", "indep_var": "...", "controls": "..." }},
            "identification": {{ "model": "...", "strategy": "...", "iv_mechanism": "..." }},
            "results": {{ "findings": "...", "weakness": "..." }},
            "stata_code": "N/A (Qualitative Paper)"
        }}
        
        # Paper Content
        {text_input}
        """

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
        mode = data.get('mode', 'QUANT')
        
        # Adjust headers based on mode
        if mode == "QUAL":
            l_theory = "核心构念"
            l_hypo = "理论框架"
            l_data = "案例选择"
            l_sample = "案例背景"
            l_dep = "结果/现象"
            l_indep = "核心条件"
            l_model = "分析方法"
            l_strat = "过程/路径"
        else:
            l_theory = "理论基础"
            l_hypo = "核心假说"
            l_data = "数据来源"
            l_sample = "样本特征"
            l_dep = "被解释变量 (Y)"
            l_indep = "核心解释变量 (X)"
            l_model = "计量模型"
            l_strat = "识别挑战与策略"

        md = f"""# {b.get('title', 'Paper Analysis')}
        
**Type**: {mode} | **Authors**: {b.get('authors', 'N/A')} | **Journal**: {b.get('journal', 'N/A')} | **Year**: {b.get('year', 'N/A')}

## 核心要素提取表 ({mode} Analysis)

| 维度 | 要素 | 内容提取 |
| :--- | :--- | :--- |
| **1. 全景扫描** | **研究主题** | {o.get('theme', '')} |
| | **科学问题** | {o.get('problem', '')} |
| | **核心贡献** | {o.get('contribution', '')} |
| **2. 理论基础** | **{l_theory}** | {t.get('theory_base', '')} |
| | **{l_hypo}** | {t.get('hypothesis', '')} |
| **3. 数据/案例** | **{l_data}** | {d.get('data_source', '')} |
| | **{l_sample}** | {d.get('sample_info', '')} |
| **4. 变量/构念** | **{l_dep}** | {m.get('dep_var', '')} |
| | **{l_indep}** | {m.get('indep_var', '')} |
| | **其他/控制** | {m.get('controls', '')} |
| **5. 策略/方法** | **{l_model}** | {i.get('model', '')} |
| | **{l_strat}** | {i.get('strategy', '')} |
| | **机制/工具** | {i.get('iv_mechanism', '')} |
| **6. 结果与评价** | **主要发现** | {r.get('findings', '')} |
| | **研究不足** | {r.get('weakness', '')} |

## 代码/附录
```stata
{data.get('stata_code', '')}
```
"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md)
