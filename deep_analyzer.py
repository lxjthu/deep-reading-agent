import os
import json
import logging
import json_repair
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class DeepAnalyzer:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Kimi for long context parsing
        self.kimi_key = os.getenv("OPENAI_API_KEY")
        self.kimi_base = os.getenv("OPENAI_BASE_URL", "https://api.moonshot.cn/v1")
        self.kimi_model = os.getenv("OPENAI_MODEL", "moonshot-v1-auto")
        
        # DeepSeek for reasoning (optional, falls back to Kimi if not set)
        self.deepseek_key = os.getenv("DEEPSEEK_API_KEY")
        self.deepseek_base = "https://api.deepseek.com"
        self.deepseek_model = "deepseek-reasoner"

        if self.kimi_key:
            self.kimi_client = OpenAI(api_key=self.kimi_key, base_url=self.kimi_base)
        else:
            self.kimi_client = None
            self.logger.warning("Kimi API Key missing.")

        if self.deepseek_key:
            self.deepseek_client = OpenAI(api_key=self.deepseek_key, base_url=self.deepseek_base)
        else:
            self.deepseek_client = None
            self.logger.info("DeepSeek API Key missing. Will use Kimi for all tasks.")

    def _call_llm(self, prompt, model_type="kimi", json_mode=True):
        """
        Helper to call LLM. 
        model_type: 'kimi' or 'deepseek'
        """
        client = self.deepseek_client if model_type == "deepseek" and self.deepseek_client else self.kimi_client
        model = self.deepseek_model if model_type == "deepseek" and self.deepseek_client else self.kimi_model
        
        if not client:
            return {"error": f"No client available for {model_type}"}

        try:
            # DeepSeek reasoner does not support response_format="json_object" yet in some versions,
            # but Kimi does. We'll handle it carefully.
            params = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "You are an expert econometrics professor (Acemoglu level). Return PURE JSON only. No markdown formatting."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2
            }
            
            # Kimi supports JSON mode enforcement
            if json_mode and model_type == "kimi":
                params["response_format"] = {"type": "json_object"}

            response = client.chat.completions.create(**params)
            content = response.choices[0].message.content
            
            # Log the raw content for debugging if it fails later
            self.logger.info(f"LLM Raw Output ({model_type}): {content[:2000]}") # Increased limit
            
            if json_mode:
                try:
                    return json_repair.repair_json(content, return_objects=True)
                except Exception as json_err:
                    self.logger.error(f"JSON Repair Failed. Raw: {content[:200]}...")
                    # Fallback: if JSON fails, return raw string to avoid N/A everywhere
                    return content
            return content

        except Exception as e:
            self.logger.error(f"LLM Call failed ({model_type}): {e}")
            return {"error": str(e)}

    def analyze_paper_deeply(self, text, filename=""):
        """
        Executes the 'Divide and Conquer' strategy for deep reading.
        Refactored to use Sequential Extraction instead of One-shot to improve stability.
        """
        self.logger.info(f"Starting deep analysis for {filename}...")
        
        results = {}
        
        # Helper for extraction prompt
        def get_extraction_prompt(section_name, context_keywords):
            return f"""
            Read the following academic paper content.
            Your task is to EXTRACT the full text content related to **{section_name}**.
            Look for keywords like: {context_keywords}.
            
            Return the extracted text directly. Do not summarize. If not found, return empty string.
            
            # Paper Text (First 150k chars)
            {text[:150000]}
            """

        # --- Phase 1: Sequential Extraction & Analysis ---
        
        # 1. Overview (Intro & Conclusion)
        self.logger.info("Processing Overview...")
        raw_overview = self._call_llm(
            get_extraction_prompt("Introduction & Conclusion", "Abstract, Introduction, Conclusion, Discussion"),
            model_type="kimi", json_mode=False
        )
        if raw_overview:
            prompt_A = f"""
            Based on the text below, answer these questions in Chinese.
            Return a strictly valid JSON object with the following keys.
            
            Questions:
            1. topic: 研究主题和结论是什么？
            2. problem: 解决了什么具体问题？
            3. importance: 为什么这些问题重要？
            4. contribution: 理论和实践贡献是什么？
            
            Example Format:
            {{
                "topic": "答案内容...",
                "problem": "答案内容...",
                "importance": "答案内容...",
                "contribution": "答案内容..."
            }}
            
            Text: {raw_overview[:50000]}
            """
            results['overview'] = self._call_llm(prompt_A, model_type="kimi", json_mode=True)
        else:
            results['overview'] = "Extraction Failed"

        # 2. Theory
        self.logger.info("Processing Theory...")
        raw_theory = self._call_llm(
            get_extraction_prompt("Theory & Literature", "Literature Review, Theoretical Framework, Hypotheses, Model"),
            model_type="kimi", json_mode=False
        )
        if raw_theory:
            prompt_B = f"""
            Based on the text below, answer in Chinese.
            Return a strictly valid JSON object with keys "5", "6", "7", "8", "9".

            Questions:
            5. 参考了哪些重要文献？
            6. 理论基础是什么？
            7. 提出了哪些待检验假说？
            8. 与前人研究有何不同？
            9. 假说的理论逻辑是什么？
            
            Example Format:
            {{
                "5": "答案...",
                "6": "答案...",
                "7": "答案...",
                "8": "答案...",
                "9": "答案..."
            }}
            
            Text: {raw_theory[:50000]}
            """
            results['theory'] = self._call_llm(prompt_B, model_type="deepseek", json_mode=True) # Use DeepSeek for theory
        else:
            results['theory'] = "Extraction Failed"

        # 3. Data
        self.logger.info("Processing Data...")
        raw_data = self._call_llm(
            get_extraction_prompt("Data & Variables", "Data, Variables, Measures, Descriptive Statistics, Sample"),
            model_type="kimi", json_mode=False
        )
        if raw_data:
            prompt_C = f"""
            Based on the text below, answer in Chinese.
            Return a strictly valid JSON object with keys "10", "11", "12", "13", "14", "15", "16", "18".

            Questions:
            10. 数据来自哪里？
            11. 公开数据如何获取/清洗？
            12. 调研数据说明（样本、抽样、代表性）。
            13. 关键被解释变量和解释变量是什么？
            14. 衡量方式？
            15. 数据来源？
            16. 是否需要特殊计算？
            18. 控制变量有哪些？选择依据是什么？
            
            Example Format:
            {{
                "10": "答案...",
                "11": "答案...",
                "12": "答案...",
                "13": "答案...",
                "14": "答案...",
                "15": "答案...",
                "16": "答案...",
                "18": "答案..."
            }}
            
            Text: {raw_data[:50000]}
            """
            results['data'] = self._call_llm(prompt_C, model_type="kimi", json_mode=True)
        else:
            results['data'] = "Extraction Failed"

        # 4. Empirical
        self.logger.info("Processing Empirical...")
        raw_empirical = self._call_llm(
            get_extraction_prompt("Empirical Results", "Empirical Strategy, Results, Robustness, Mechanism, Identification"),
            model_type="kimi", json_mode=False
        )
        if raw_empirical:
            prompt_D = f"""
            Based on the text below, answer in Chinese.
            Return a strictly valid JSON object with the following keys.

            Questions:
            19. model: 使用了什么计量模型？
            20. robustness: 如何进行稳健性、内生性、异质性、机制分析？
            
            Example Format:
            {{
                "model": "答案...",
                "robustness": "答案..."
            }}
            
            Text: {raw_empirical[:50000]}
            """
            results['empirical'] = self._call_llm(prompt_D, model_type="deepseek", json_mode=True) # Use DeepSeek for econometrics
        else:
            results['empirical'] = "Extraction Failed"
        
        # --- Phase 2: Synthesis ---
        
        # Synthesis (DeepSeek)
        self.logger.info("Synthesizing Report...")
        prompt_E = f"""
        Synthesize the analysis below and generate (return JSON):
        17. Mechanism Map (Mermaid code format) showing interactions between key variables.
        21. Future research directions based on limitations.
        22. Expert Critique (Achilles' Heel).
        
        Inputs:
        Theory: {json.dumps(results.get('theory', {}), ensure_ascii=False)}
        Empirical: {json.dumps(results.get('empirical', {}), ensure_ascii=False)}
        """
        results['synthesis'] = self._call_llm(prompt_E, model_type="deepseek", json_mode=True)
        
        return results

    def generate_deep_report(self, data, output_path):
        """
        Generates the Acemoglu-style deep reading report.
        """
        # Helper to safely get string from potentially nested JSON or string
        def get_str(source, *keys):
            if isinstance(source, str):
                return source[:500] + "..." if len(source) > 500 else source
            
            if not isinstance(source, dict):
                return "N/A"

            # Try exact match for all provided keys
            for key in keys:
                val = source.get(key)
                if val is not None:
                    break
                # Try string version of int keys just in case
                val = source.get(str(key))
                if val is not None:
                    break
            
            # If still None, try fuzzy match with the first key (usually the English name)
            if val is None and keys:
                primary_key = str(keys[0])
                for k in source.keys():
                    if primary_key.lower() in k.lower():
                        val = source[k]
                        break
            
            if val is None:
                return "N/A"
                
            if isinstance(val, (dict, list)):
                return json.dumps(val, ensure_ascii=False, indent=2)
            return str(val)

        overview = data.get('overview', {})
        theory = data.get('theory', {})
        data_sec = data.get('data', {})
        emp = data.get('empirical', {})
        syn = data.get('synthesis', {})

        # If any section is a string (failed JSON parse), we dump the whole content under a general section
        # to ensure no data loss.
        
        md = f"""# 深度研读报告 (Acemoglu Level)

## 1. 研究全景 (Overview)
- **核心主题与结论**: {get_str(overview, 'topic')}
- **问题意识**: {get_str(overview, 'problem')}
- **重要性**: {get_str(overview, 'importance')}
- **贡献定位**: {get_str(overview, 'contribution')}
*(Raw Output if JSON failed: {json.dumps(overview, ensure_ascii=False) if isinstance(overview, dict) else overview})*

## 2. 理论脉络 (Theoretical Framework)
- **核心文献**: {get_str(theory, 'literature')}
- **理论基础**: {get_str(theory, 'basis')}
- **研究假说**: {get_str(theory, 'hypothesis')}
- **创新点**: {get_str(theory, 'novelty')}
- **理论逻辑**: {get_str(theory, 'logic')}
*(Raw Output if JSON failed: {json.dumps(theory, ensure_ascii=False) if isinstance(theory, dict) else theory})*

## 3. 数据与变量 (Data & Variables)
- **数据来源**: {get_str(data_sec, 'source')}
- **数据获取/清洗**: {get_str(data_sec, 'cleaning')}
- **调研详情**: {get_str(data_sec, 'survey')}
- **核心变量**: {get_str(data_sec, 'vars')} ({get_str(data_sec, 'measure')})
- **控制变量**: {get_str(data_sec, 'controls')}
*(Raw Output if JSON failed: {data_sec if isinstance(data_sec, str) else ''})*

## 4. 影响机制图谱 (Mechanism Map)
```mermaid
{get_str(syn, 'mechanism')}
```

## 5. 实证策略 (Empirical Strategy)
- **计量模型**: {get_str(emp, 'model')}
- **识别策略与稳健性**: {get_str(emp, 'robustness')}
*(Raw Output if JSON failed: {json.dumps(emp, ensure_ascii=False) if isinstance(emp, dict) else emp})*

## 6. 专家批判与展望 (Critique & Future)
- **致命伤 (Critique)**: {get_str(syn, 'critique')}
- **未来选题**: {get_str(syn, 'future')}
*(Raw Output if JSON failed: {json.dumps(syn, ensure_ascii=False) if isinstance(syn, dict) else syn})*
"""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(md)
