import os
import json
import logging
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
import re
import difflib

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# LLM Configuration
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-reasoner" # Using reasoner for Acemoglu-level thinking

DEEP_READING_DIR = os.getenv("DEEP_READING_OUTPUT_DIR", os.path.join(os.getcwd(), "deep_reading_results"))

def get_deepseek_client():
    if not DEEPSEEK_API_KEY:
        logger.error("DEEPSEEK_API_KEY not found in environment variables.")
        return None
    return OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE_URL)

def get_combined_text_for_step(sections, assigned_titles, output_dir=None, step_id=None):
    """
    Retrieves and combines text for a list of assigned section titles.
    Priority 1: Load from Semantic Index (if available and step_id provided).
    Priority 2: Load from 'sections' dict with Next-Section Fallback.
    """
    combined_text = ""
    
    # Priority 1: Semantic Index (JSON)
    if output_dir and step_id:
        index_path = os.path.join(output_dir, "semantic_index.json")
        if os.path.exists(index_path):
            try:
                with open(index_path, 'r', encoding='utf-8') as f:
                    index_data = json.load(f)
                    chunks = index_data.get("chunks", [])
                    # Filter chunks tagged with this step_id
                    relevant_chunks = [c["text"] for c in chunks if step_id in c.get("tags", [])]
                    
                    if relevant_chunks:
                        logger.info(f"Loaded {len(relevant_chunks)} chunks from Semantic Index for Step {step_id}")
                        return "\n\n".join(relevant_chunks)
            except Exception as e:
                logger.error(f"Failed to load Semantic Index: {e}")

    # Priority 2: Traditional Section Retrieval (Fallback)
    all_titles = list(sections.keys())
    
    for title in assigned_titles:
        if title not in sections:
            continue
            
        text = sections[title].strip()
        combined_text += f"【{title}】\n{text}\n\n"
        
        # Fallback Logic: If text is too short (< 100 chars), grab the next section
        if len(text) < 100:
            try:
                current_idx = all_titles.index(title)
                if current_idx + 1 < len(all_titles):
                    next_title = all_titles[current_idx + 1]
                    next_text = sections[next_title].strip()
                    combined_text += f"【{title} (Continued from {next_title})】\n{next_text}\n\n"
                    logger.info(f"Fallback triggered: Appended {next_title} to {title}")
            except ValueError:
                pass
                
    if not combined_text.strip():
        combined_text = "No content found for assigned sections."
    
    # Text Cleaning: Merge broken lines
    # ... (rest of cleaning logic remains the same)
    # 1. First, temporarily replace real paragraph breaks (\n\n) with a placeholder
    cleaned_text = combined_text.replace('\n\n', '<<PARA>>')
    
    # 2. Split by single newline
    lines = cleaned_text.split('\n')
    merged_lines = []
    current_line = ""
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # If current line ends with a sentence-ending punctuation, assume it's a real break
        # Otherwise, merge with next
        if current_line:
            # Check if previous line ended with punctuation (keep space if English, no space if Chinese)
            if re.search(r'[。？！.?!]$', current_line):
                 merged_lines.append(current_line)
                 current_line = line
            else:
                 # Check if Chinese char (no space) or English (space)
                 if re.search(r'[\u4e00-\u9fa5]$', current_line):
                     current_line += line
                 else:
                     current_line += " " + line
        else:
            current_line = line
            
    if current_line:
        merged_lines.append(current_line)
        
    cleaned_text = "\n".join(merged_lines)
    
    # 3. Restore paragraph breaks
    cleaned_text = cleaned_text.replace('<<PARA>>', '\n\n')
    
    return cleaned_text

def call_deepseek(prompt, system_prompt="You are a helpful assistant."):
    # Enforce Clean Academic Output & Anti-Hallucination
    system_prompt += "\n\nIMPORTANT RULES:\n1. Directly output the analysis content. Do not include any opening remarks, greetings, meta-commentary, or fillers like 'Okay, I will...'.\n2. NO HALLUCINATIONS: If the provided text is empty, insufficient, or unrelated to the prompt questions, state 'No content found' clearly. DO NOT invent data, variables, or results based on general knowledge."
    
    client = get_deepseek_client()
    if not client:
        return None

    try:
        response = client.chat.completions.create(
            model=DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            stream=False
        )
        return response.choices[0].message.content
    except Exception as e:
        logger.error(f"DeepSeek API call failed: {e}")
        return None

def load_segmented_md(md_path):
    """
    Parses the segmented markdown file into a dictionary of sections.
    Keys are section titles (or approximation), values are text content.
    """
    if not os.path.exists(md_path):
        logger.error(f"Segmented MD file not found: {md_path}")
        return {}

    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Simple parsing based on "## " headers
    sections = {}
    current_section = None
    current_text = []

    for line in content.split('\n'):
        if line.startswith("## "):
            if current_section:
                sections[current_section] = "\n".join(current_text).strip()
            current_section = line.strip("# ").strip()
            current_text = []
        else:
            current_text.append(line)
    
    if current_section:
        sections[current_section] = "\n".join(current_text).strip()

    return sections

def save_step_result(step_name, result, output_dir=None):
    if output_dir is None:
        output_dir = DEEP_READING_DIR
        
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    output_path = os.path.join(output_dir, f"{step_name}.md")
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result)
    logger.info(f"Saved result for {step_name} to {output_path}")
    return output_path

def smart_chunk(text, max_tokens=8000):
    """
    智能分块：将长文本按段落边界切分为多个块，避免截断。
    """
    max_chars = max_tokens * 3
    if len(text) <= max_chars:
        return [text]
    
    paragraphs = text.split('\n\n')
    chunks = []
    current_chunk = []
    current_len = 0
    
    for para in paragraphs:
        para_len = len(para)
        if para_len > max_chars:
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_len = 0
            
            sentences = para.replace('。', '。\n').replace('. ', '.\n').split('\n')
            for sent in sentences:
                if current_len + len(sent) > max_chars and current_chunk:
                    chunks.append('\n\n'.join(current_chunk))
                    current_chunk = [sent]
                    current_len = len(sent)
                else:
                    current_chunk.append(sent)
                    current_len += len(sent)
        else:
            if current_len + para_len > max_chars and current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = [para]
                current_len = para_len
            else:
                current_chunk.append(para)
                current_len += para_len + 2 
    
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    return chunks

def find_section_with_fallback(sections, keywords, fallback_keywords=None):
    context_text = ""
    found_primary = False
    
    for title, text in sections.items():
        if any(kw in title for kw in keywords):
            context_text += f"【{title}】\n{text}\n\n"
            found_primary = True
    
    if not found_primary and fallback_keywords:
        logger.warning(f"未找到主要关键词 {keywords}，尝试 fallback: {fallback_keywords}")
        for title, text in sections.items():
            if any(kw in title for kw in fallback_keywords):
                context_text += f"【{title}】\n{text}\n\n"
    
    if not context_text:
        logger.warning(f"未找到匹配 {keywords} 或 {fallback_keywords} 的章节")
        context_text = f"未找到明确的相关章节（搜索关键词：{keywords}）。请尝试从全文其他部分推断。"
    
    return context_text

def route_sections_to_steps(sections: dict) -> dict:
    """
    混合路由策略：
    1. 尝试 LLM 动态映射（支持多标签）。
    2. 对匹配失败的标题使用本地规则兜底。
    3. 确保每个步骤都有内容（位置兜底）。
    """
    section_titles = list(sections.keys())
    if not section_titles:
        logger.error("No sections found for routing")
        return {str(i): [] for i in range(1, 8)}

    # 1. 尝试 LLM 路由
    llm_routing = _llm_routing(section_titles)
    
    # 2. 本地规则兜底 (用于补充 LLM 可能遗漏的或填充空步骤)
    rule_routing = _rule_based_routing(section_titles)
    
    # 3. 合并逻辑
    final_routing = {i: [] for i in range(1, 8)}
    
    # 优先使用 LLM 结果
    if llm_routing:
        final_routing = llm_routing
    
    # 检查是否有空步骤，若有则用规则结果填充
    for step in range(1, 8):
        if not final_routing.get(step):
            logger.info(f"Step {step} empty after LLM routing, using rule-based fallback.")
            final_routing[step] = rule_routing.get(step, [])
            
    # 4. 最终的位置兜底 (如果规则也没匹配上)
    _apply_positional_fallback(final_routing, section_titles)
    
    return final_routing

def _llm_routing(section_titles: list) -> dict:
    """
    调用 LLM 生成动态映射表
    """
    import json
    section_list_str = json.dumps(section_titles, indent=2, ensure_ascii=False)
    
    system_prompt = """你是论文结构分析专家。你的任务是将论文的章节标题映射到 7 个标准的精读步骤中。
    
    关键规则：
    1. **多标签支持**：一个章节标题可以（且应该）被分配给多个相关的步骤。例如“研究设计”通常包含数据、变量和模型，因此应同时分配给 Step 3, 4, 5。
    2. **完全匹配**：请直接使用输入的章节标题字符串，不要修改、缩写或翻译。
    3. **中文语境**：注意中文论文中“引言”可能体现为“问题的提出”或无标题段落（如 Preface）。
    
    精读步骤定义：
    - Step 1 (Overview): Abstract, Introduction, Conclusion, 摘要, 引言, 问题的提出
    - Step 2 (Theory): Literature Review, Theory, Hypothesis, Background, 文献, 理论, 假说, 背景
    - Step 3 (Data): Data, Sample, Source, 数据, 样本, 来源
    - Step 4 (Variables): Variables, Measurement, Definition, 变量, 测度, 指标, 定义
    - Step 5 (Identification): Model, Method, Strategy, Identification, 模型, 方法, 策略, 识别
    - Step 6 (Results): Results, Findings, Empirical, Discussion, 结果, 实证, 讨论, 分析
    - Step 7 (Critique): Conclusion, Limitation, Future, 结论, 局限, 展望
    """
    
    user_prompt = f"""请为以下章节标题生成 JSON 映射表。
    
    章节列表：
    {section_list_str}
    
    输出格式（JSON）：
    {{
      "routing": {{
        "1": ["标题A", "标题B"],
        "2": ["标题C"],
        ...
        "7": ["标题X"]
      }}
    }}
    """
    
    logger.info("Requesting LLM for dynamic routing map...")
    result = call_deepseek(user_prompt, system_prompt)
    
    if not result:
        return {}
        
    try:
        import json_repair
        data = json_repair.repair_json(result, return_objects=True)
        raw_routing = data.get("routing", {})
        
        # 转换并校验 Key
        validated_routing = {i: [] for i in range(1, 8)}
        for step_str, titles in raw_routing.items():
            step_id = int(step_str)
            if 1 <= step_id <= 7:
                for t in titles:
                    # 模糊匹配校验：找到最接近的真实标题
                    real_title = _fuzzy_match_title(t, section_titles)
                    if real_title:
                        if real_title not in validated_routing[step_id]:
                            validated_routing[step_id].append(real_title)
        
        return validated_routing
    except Exception as e:
        logger.error(f"LLM Routing parsing failed: {e}")
        return {}

def _fuzzy_match_title(target, candidates):
    """
    在 candidates 中找到与 target 最相似的标题。
    用于处理 LLM 可能产生的细微标点或空格差异。
    """
    if target in candidates:
        return target
        
    # 尝试去标点去空格匹配
    def normalize(s):
        return re.sub(r'\s+|[^\w\u4e00-\u9fa5]', '', s).lower()
        
    target_norm = normalize(target)
    for cand in candidates:
        if normalize(cand) == target_norm:
            return cand
            
    # 使用 difflib 找最相似
    matches = difflib.get_close_matches(target, candidates, n=1, cutoff=0.8)
    return matches[0] if matches else None

def _rule_based_routing(section_titles: list) -> dict:
    """
    增强的本地规则路由（双语 + 多标签）
    """
    routing = {i: [] for i in range(1, 8)}
    
    # 关键词库 (Lower case for matching)
    keywords = {
        1: ["abstract", "introduction", "overview", "preface", "摘要", "引言", "绪论", "问题的提出", "研究背景"],
        2: ["literature", "theory", "hypothesis", "background", "framework", "文献", "理论", "假说", "假设", "背景", "框架", "机理", "逻辑"],
        3: ["data", "sample", "source", "material", "design", "数据", "样本", "来源", "资料", "设计"],
        4: ["variable", "measure", "indicator", "descriptive", "definition", "design", "变量", "测度", "测量", "指标", "描述", "定义", "设计"],
        5: ["model", "method", "strategy", "identification", "equation", "design", "模型", "方法", "策略", "识别", "方程", "设计"],
        6: ["result", "finding", "empirical", "analysis", "discussion", "结果", "发现", "实证", "分析", "回归", "检验"],
        7: ["conclusion", "limitation", "policy", "implication", "future", "discussion", "结论", "局限", "不足", "政策", "启示", "展望", "结语"]
    }
    
    exclude_keywords = ["reference", "参考文献", "appendix", "附录", "acknowledgement", "致谢"]

    for title in section_titles:
        title_lower = title.lower()
        
        # 跳过排除项
        if any(kw in title_lower for kw in exclude_keywords):
            continue
            
        # 特殊处理：无标题引言 (Preface / 空标题)
        if title in ["", "Preface", "Unknown"] or title.strip() == "":
            routing[1].append(title)
            continue
            
        # 多标签匹配
        matched_any = False
        for step, kws in keywords.items():
            if any(kw in title_lower for kw in kws):
                if title not in routing[step]:
                    routing[step].append(title)
                matched_any = True
        
        # 如果没匹配上任何步骤，根据位置放入
        if not matched_any:
            # 暂时不处理，留给位置兜底
            pass
            
    return routing

def _apply_positional_fallback(routing, section_titles):
    """
    位置兜底：确保每个步骤都有内容
    """
    total = len(section_titles)
    if total == 0:
        return

    # 简单的分段索引
    idx_p25 = int(total * 0.25)
    idx_p65 = int(total * 0.65)
    
    # Step 1-2 (Front)
    for s in [1, 2]:
        if not routing[s]:
            routing[s] = section_titles[:idx_p25+1]
            
    # Step 3-5 (Middle)
    for s in [3, 4, 5]:
        if not routing[s]:
            # 取中间部分，如果没有中间，就取全部
            start = idx_p25
            end = idx_p65 + 1
            if start >= end:
                start = 0
                end = total
            routing[s] = section_titles[start:end]

    # Step 6-7 (End)
    for s in [6, 7]:
        if not routing[s]:
            routing[s] = section_titles[idx_p65:]

def save_routing_result(routing: dict, sections: dict, output_dir: str):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    output_path = os.path.join(output_dir, "section_routing.md")
    
    lines = [
        "# Section Routing Result (Hybrid Engine)",
        "",
        f"Generated at: {datetime.now().isoformat()}",
        "",
    ]
    
    step_names = {
        1: "Overview (全景扫描)",
        2: "Theory (理论与假说)",
        3: "Data (数据考古)",
        4: "Variables (变量与测量)",
        5: "Identification (识别策略)",
        6: "Results (结果解读)",
        7: "Critique (专家批判)"
    }
    
    for step_num in range(1, 8):
        assigned = routing.get(step_num, [])
        lines.append(f"## Step {step_num}: {step_names[step_num]}")
        if assigned:
            for sec_name in assigned:
                lines.append(f"- {sec_name}")
        else:
            lines.append("- ⚠️ No sections assigned")
        lines.append("")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("\n".join(lines))
    
    logger.info(f"Saved routing result to {output_path}")
    return output_path
