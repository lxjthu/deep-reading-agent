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

        # Kimi (Moonshot AI) supports very long context (up to 128k tokens).
        # We can be much more generous with the input limit.
        # 1 token approx 1.5 - 2 chars for Chinese/English mix. 
        # 128k tokens ~ 200k chars. Let's set a safe limit of 150k chars.
        if len(text) > 150000:
            text_input = text[:100000] + "\n\n...[Middle section omitted]...\n\n" + text[-50000:]
        else:
            text_input = text

        prompt = f"""
        You are an expert in Econometrics and Academic Research. 
        Analyze the following academic paper content (extracted from PDF) and extract structured information.
        
        Paper Filename: {filename}
        
        # Requirements
        Extract the following fields and return them in a valid JSON format.
        
        1. **General Info**:
           - title: Paper title (inferred)
           - background: Research background (200-300 words summary)
           - significance: Theoretical and Practical significance
           - logic: Research logic/flow (describe as text, mentions of flowcharts)
           - methodology_summary: Detailed step-by-step methodology
           - conclusions: 3-5 core findings
           
        2. **Academic Variables** (Crucial):
           - dependent_variable: Name + Definition
           - independent_variable: Name + Definition
           - mechanism_variable: Name + Definition
           - instrumental_variable: Name + Definition
           - control_variables: List of controls
           
        3. **Data & Methods**:
           - variable_measurements: How variables are measured
           - data_source: Data sources description
           - references: Key references in citation format
           
        4. **Stata Code**:
           - stata_code: Generate expert-level Stata code corresponding to the methodology mentioned (e.g., DID, IV, Fixed Effects). Include comments.
           
        # Output Format
        Return ONLY valid JSON. No markdown formatting like ```json ... ```.
        Structure:
        {{
            "title": "...",
            "background": "...",
            "significance": "...",
            "logic": "...",
            "methodology_summary": "...",
            "conclusions": "...",
            "variables": {{
                "dependent": "...",
                "independent": "...",
                "mechanism": "...",
                "instrumental": "...",
                "controls": "..."
            }},
            "data_methods": {{
                "measurements": "...",
                "data_source": "...",
                "references": "..."
            }},
            "stata_code": "..."
        }}
        
        # Paper Content
        {text_input}
        """

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a helpful academic research assistant."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1, # Low temperature for factual extraction
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            
            # Use json_repair to handle potentially malformed JSON
            try:
                return json_repair.repair_json(content, return_objects=True)
            except Exception as json_err:
                self.logger.error(f"JSON Parsing failed even with repair: {json_err}")
                self.logger.debug(f"Raw content: {content}")
                return {"error": f"JSON Parse Error: {str(json_err)}"}
            
        except Exception as e:
            self.logger.error(f"LLM Analysis failed: {e}")
            return {"error": str(e)}

    def generate_markdown_report(self, data, output_path):
        """
        Converts the JSON analysis into a readable Markdown report.
        """
        if "error" in data:
            return
            
        md = f"""# {data.get('title', 'Paper Analysis')}

## 1. 总体信息提取
### 研究背景
{data.get('background', 'N/A')}

### 研究意义
{data.get('significance', 'N/A')}

### 研究思路
{data.get('logic', 'N/A')}

### 研究方法
{data.get('methodology_summary', 'N/A')}

### 研究结论
{data.get('conclusions', 'N/A')}

## 2. 具体学术要素提取
### 变量信息
- **关键被解释变量**: {data.get('variables', {}).get('dependent', 'N/A')}
- **解释变量**: {data.get('variables', {}).get('independent', 'N/A')}
- **机制变量**: {data.get('variables', {}).get('mechanism', 'N/A')}
- **工具变量**: {data.get('variables', {}).get('instrumental', 'N/A')}
- **控制变量**: {data.get('variables', {}).get('controls', 'N/A')}

## 3. 数据与方法
### 变量测算
{data.get('data_methods', {}).get('measurements', 'N/A')}

### 数据来源
{data.get('data_methods', {}).get('data_source', 'N/A')}

### 相关参考文献
{data.get('data_methods', {}).get('references', 'N/A')}

## 4. Stata 代码建议
```stata
{data.get('stata_code', '')}
```
"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md)
