import os
import json
import logging
from .common import smart_chunk, call_deepseek

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一个专业的学术论文结构分析师。
你的任务是阅读给定的论文文本片段，并判断该片段主要包含以下哪些部分的内容。

这是一个索引任务，不需要你重写原文。只需判断原文片段归属于哪个部分，以便下游程序进行提取。

分析步骤定义：
1. **Overview (全景扫描)**: 摘要、引言、结论摘要、研究背景、核心贡献。
2. **Theory (理论与假说)**: 文献综述、理论框架、研究假设、制度背景。
3. **Data (数据考古)**: 数据来源、样本选择、数据清洗、变量定义、描述性统计。
4. **Variables (变量与测量)**: 核心变量(X, Y)定义、控制变量、模型设定。
5. **Identification (识别策略)**: 计量模型公式、内生性讨论、工具变量、DID/RDD设计、机制检验设计。
6. **Results (结果解读)**: 实证结果、回归表格分析、稳健性检验、异质性分析。
7. **Critique (专家批判)**: 研究局限、未来展望、政策建议。

重要原则：
- **宁滥勿缺 (Better safe than sorry)**：如果片段内容跨越多个部分，或者你不能确定，请包含所有可能相关的步骤编号。
- **完整性**：如果片段包含数据描述，即使只有几句话，也要标记为 3 (Data)，不要因为内容简短而忽略。

请返回一个 JSON 列表，包含该片段涉及的所有步骤编号（1-7）。
例如：[2, 3] 表示该片段包含理论和数据相关内容。
如果片段是参考文献或无关信息，返回 []。
"""

def generate_semantic_index(full_text, output_dir):
    """
    Splits the full text into chunks, asks LLM to tag each chunk with step IDs,
    and saves the result to semantic_index.json.
    """
    logger.info("Starting Semantic Indexing...")
    
    # 1. Split text into manageable chunks (e.g., 6k tokens ~ 18k chars)
    chunks = smart_chunk(full_text, max_tokens=6000)
    logger.info(f"Split text into {len(chunks)} chunks.")
    
    indexed_chunks = []
    
    for i, chunk in enumerate(chunks):
        logger.info(f"Indexing chunk {i+1}/{len(chunks)}...")
        
        # Call LLM to tag the chunk
        prompt = f"请分析以下论文片段，判断它属于哪些分析步骤（返回 [1, 2, ...] 格式）：\n\n{chunk[:5000]}..." # Truncate for prompt if needed, but smart_chunk should handle it.
        
        # Use a strict JSON prompt
        response = call_deepseek(prompt, SYSTEM_PROMPT + "\n\n只返回 JSON 数组，例如：[1, 3]")
        
        tags = []
        if response:
            try:
                # Simple parsing to find the list
                import re
                match = re.search(r'\[.*?\]', response)
                if match:
                    tags = json.loads(match.group(0))
                    # Validate tags
                    tags = [t for t in tags if isinstance(t, int) and 1 <= t <= 7]
            except Exception as e:
                logger.error(f"Failed to parse tags for chunk {i}: {e}")
        
        logger.info(f"Chunk {i+1} tags: {tags}")
        
        indexed_chunks.append({
            "id": i,
            "text": chunk,
            "tags": tags
        })
    
    # Save to file
    index_path = os.path.join(output_dir, "semantic_index.json")
    with open(index_path, 'w', encoding='utf-8') as f:
        json.dump({"chunks": indexed_chunks}, f, ensure_ascii=False, indent=2)
        
    logger.info(f"Semantic index saved to {index_path}")
    return index_path
