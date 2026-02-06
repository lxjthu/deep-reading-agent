"""
智能分段路由器 - 新版分段方案
LLM 只负责分类标注，内容切分由代码完成
"""

import os
import re
import json
import logging
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
import json_repair

load_dotenv()

logger = logging.getLogger(__name__)


@dataclass
class Heading:
    """标题结构"""
    level: int          # 1=#, 2=##, 3=###
    title: str         # 标题文本
    start_pos: int     # 在原文中的起始位置
    end_pos: int       # 在原文中的结束位置（下一个标题前或EOF）


class SmartSegmentRouter:
    """
    智能分段路由器
    
    工作流程:
    1. 解析 PaddleOCR MD，提取所有 ##/### 标题
    2. 将标题列表发给 LLM，获取步骤标签映射
    3. 根据标签直接切分原文，保证内容完整
    4. 输出兼容现有格式的 segmented.md
    """
    
    # 7步精读标签定义
    QUANT_STEPS = {
        1: "Overview (全景扫描) - 摘要、引言、结论、研究背景、核心贡献",
        2: "Theory (理论与假说) - 文献综述、理论框架、研究假设",
        3: "Data (数据考古) - 数据来源、样本选择、数据清洗",
        4: "Variables (变量与测量) - 核心变量定义、测量方法、描述性统计", 
        5: "Identification (识别策略) - 计量模型、内生性讨论、IV/DID/RDD",
        6: "Results (结果解读) - 实证结果、回归分析、稳健性检验",
        7: "Critique (专家批判) - 研究局限、未来展望、政策建议"
    }
    
    # 4层金字塔标签定义
    QUAL_STEPS = {
        "L1": "L1_Context (背景层) - 摘要、引言、政策背景、现状数据",
        "L2": "L2_Theory (理论层) - 文献综述、理论框架、核心构念",
        "L3": "L3_Logic (逻辑层) - 方法设计、案例分析、机制路径、实证结果",
        "L4": "L4_Value (价值层) - 结论、讨论、研究缺口、理论贡献、实践启示"
    }
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        self.client = None
        if self.api_key:
            self.client = OpenAI(api_key=self.api_key, base_url="https://api.deepseek.com")
    
    def extract_headings(self, content: str) -> List[Heading]:
        """
        从 PaddleOCR MD 中提取章节标题
        
        策略:
        - 优先提取 ### 三级章节标题（1. Introduction, 2. Literature 等）
        - 如果没有 ###，则提取 ## 二级标题
        - 如果有 ###，则忽略 ## Text Content 这种容器章节
        - 记录每个标题在原文中的位置，用于后续切分
        """
        headings = []
        
        # 提取所有 ### 标题（三级章节）
        pattern_h3 = r'^#{3}\s+(.+?)$'
        h3_headings = []
        for match in re.finditer(pattern_h3, content, re.MULTILINE):
            title = match.group(1).strip()
            start_pos = match.start()
            h3_headings.append(Heading(
                level=3,
                title=title,
                start_pos=start_pos,
                end_pos=-1
            ))
        
        # 如果有 ### 标题，使用 ### 作为主要切分点
        if len(h3_headings) >= 3:
            headings = h3_headings
            logger.info(f"Using level-3 (###) headings: {len(headings)} found")
        else:
            # 否则提取 ## 标题（二级章节）
            pattern_h2 = r'^#{2}\s+(.+?)$'
            for match in re.finditer(pattern_h2, content, re.MULTILINE):
                title = match.group(1).strip()
                start_pos = match.start()
                headings.append(Heading(
                    level=2,
                    title=title,
                    start_pos=start_pos,
                    end_pos=-1
                ))
            logger.info(f"Using level-2 (##) headings: {len(headings)} found")
        
        # 计算每个标题的结束位置（下一个同级标题前或文件尾）
        for i, h in enumerate(headings):
            if i + 1 < len(headings):
                h.end_pos = headings[i + 1].start_pos
            else:
                h.end_pos = len(content)
        
        return headings
    
    def _detect_paper_type(self, headings: List[str]) -> str:
        """
        根据标题内容自动检测论文类型 (quant/qual)
        """
        heading_text = ' '.join(headings).lower()
        
        # 定量论文关键词
        quant_keywords = ['regression', 'ols', 'did', 'iv', 'rdd', 'panel data', 
                         'robustness', 'endogeneity', '系数', '回归', '稳健性',
                         '实证分析', '计量模型', '内生性']
        
        # 定性论文关键词
        qual_keywords = ['case study', 'grounded theory', 'qca', 'qualitative',
                        'interview', '案例研究', '扎根理论', '访谈', '质性研究']
        
        quant_score = sum(1 for k in quant_keywords if k in heading_text)
        qual_score = sum(1 for k in qual_keywords if k in heading_text)
        
        return "quant" if quant_score >= qual_score else "qual"
    
    def _build_classification_prompt(self, headings: List[str], mode: str) -> str:
        """构建分类提示词"""
        
        # 过滤掉非章节标题（如 Text Content、References 等）
        skip_keywords = ['text content', 'references', 'appendix', '致谢', '参考文献', '附录']
        filtered_headings = [h for h in headings if not any(kw in h.lower() for kw in skip_keywords)]
        
        if mode == "quant":
            steps_desc = "\n".join([f"  步骤{k}: {v}" for k, v in self.QUANT_STEPS.items()])
            example = '''{
  "routing": {
    "1": ["Abstract", "1. Introduction", "一、引言"],
    "2": ["2. Literature Review", "3. Theoretical Framework", "二、理论框架", "文献综述"],
    "3": ["4. Data and Sample", "三、实证设计", "数据说明", "样本选择"],
    "4": ["4.1 Variable Definition", "变量定义", "描述性统计", "研究设计"],
    "5": ["5. Empirical Strategy", "计量模型", "识别策略", "内生性处理", "工具变量", "研究设计"],
    "6": ["6. Results", "四、实证结果", "基准回归", "机制分析", "异质性分析", "稳健性检验"],
    "7": ["7. Conclusion", "五、结论", "政策建议", "研究局限"]
  },
  "multi_assign": {
    "研究设计": ["3", "4", "5"],
    "实证设计": ["3", "4", "5"]
  },
  "mode": "quant",
  "notes": ["重要：一个章节可能同时包含多个步骤的内容，如'研究设计'通常同时包含数据、变量、模型，请将其分配到多个步骤"]
}'''
        else:  # qual
            steps_desc = "\n".join([f"  {k}: {v}" for k, v in self.QUAL_STEPS.items()])
            example = '''{
  "routing": {
    "L1": ["摘要", "1. 引言", "一、研究背景"],
    "L2": ["2. 文献综述", "3. 理论框架", "二、理论基础"],
    "L3": ["4. 研究设计", "5. 案例分析", "6. 实证结果", "三、实证分析"],
    "L4": ["7. 结论与启示", "8. 研究展望", "四、结论"]
  },
  "mode": "qual",
  "notes": ["第一章引言归入L1背景层"]
}'''
        
        return f"""请分析以下论文章节标题，将每个标题映射到对应的分析步骤。

分析步骤定义：
{steps_desc}

论文章节列表：
{json.dumps(headings, ensure_ascii=False, indent=2)}

任务：
1. 为每个标题选择最合适的分析步骤编号
2. **重要：一个章节可以同时属于多个步骤**。例如：
   - "研究设计" / "实证设计" / "Empirical Strategy" 通常同时包含数据、变量、模型，应该同时分配到步骤3、4、5
   - "方法" / "Methodology" 可能同时包含变量定义和模型，应该同时分配到步骤4、5
3. 在 routing 中放置主要分类，在 multi_assign 中放置多步骤映射
4. 如果是不重要的章节（如参考文献、致谢），放入 "skip"

输出格式（严格JSON）：
{example}

重要规则：
- 使用输入的标题原文，不要修改或翻译
- 鼓励多步骤映射：如果一个章节可能属于多个步骤，请使用 multi_assign
- "研究设计" 默认应该映射到 ["3", "4", "5"]
- "skip" 列表中放置不重要的章节（如参考文献、致谢）
"""
    
    def classify_headings(self, headings: List[Heading], mode: str = "auto") -> Tuple[Dict[str, List[str]], str]:
        """
        使用 LLM 对标题进行分类标注
        
        Returns:
            (routing_dict, detected_mode)
            routing_dict: {step_id: [title1, title2, ...]}
        """
        # 只送 ## 级别（level=2）给 LLM，### 级别作为子内容跟随父章节
        primary_headings = [h.title for h in headings if h.level == 2]
        
        if len(primary_headings) == 0:
            # 如果没有 ## 标题，尝试用 ###
            primary_headings = [h.title for h in headings if h.level == 3]
        
        if mode == "auto":
            mode = self._detect_paper_type(primary_headings)
            logger.info(f"Auto-detected paper mode: {mode}")
        
        if not self.client:
            logger.warning("No DeepSeek API key, using fallback classification")
            return self._fallback_classification(headings, mode), mode
        
        prompt = self._build_classification_prompt(primary_headings, mode)
        
        try:
            logger.info(f"Sending classification request for {len(primary_headings)} headings...")
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你是学术论文结构分析专家。只输出JSON，不添加解释。"},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            result = json_repair.repair_json(content, return_objects=True)
            
            routing = result.get("routing", {})
            multi_assign = result.get("multi_assign", {})
            
            # 处理多步骤映射：一个标题可以属于多个步骤
            for title, step_ids in multi_assign.items():
                for step_id in step_ids:
                    if step_id not in routing:
                        routing[step_id] = []
                    if title not in routing[step_id]:
                        routing[step_id].append(title)
            
            logger.info(f"LLM classification result: {routing}")
            
            return routing, mode
            
        except Exception as e:
            logger.error(f"LLM classification failed: {e}")
            return self._fallback_classification(headings, mode), mode
    
    def _fallback_classification(self, headings: List[Heading], mode: str) -> Dict[str, List[str]]:
        """
        基于规则的回退分类（当 LLM 失败时使用）
        """
        routing = {}
        
        if mode == "quant":
            keywords = {
                "1": ["abstract", "introduction", "摘要", "引言"],
                "2": ["literature", "theory", "文献", "理论"],
                "3": ["data", "sample", "数据", "样本"],
                "4": ["variable", "measure", "变量", "测量"],
                "5": ["model", "method", "empirical", "模型", "方法", "实证"],
                "6": ["result", "finding", "结果", "发现"],
                "7": ["conclusion", "limitation", "结论", "局限"]
            }
        else:
            keywords = {
                "L1": ["abstract", "introduction", "摘要", "引言", "背景"],
                "L2": ["literature", "theory", "文献", "理论", "综述"],
                "L3": ["method", "result", "case", "方法", "结果", "案例", "分析"],
                "L4": ["conclusion", "discussion", "结论", "讨论", "启示"]
            }
        
        for step_id, kws in keywords.items():
            routing[step_id] = []
        
        # 支持多步骤映射的标题
        multi_step_titles = {
            "研究设计": ["3", "4", "5"],
            "实证设计": ["3", "4", "5"],
            "methodology": ["3", "4", "5"],
            "empirical strategy": ["3", "4", "5"]
        }
        
        for h in headings:
            title_lower = h.title.lower()
            
            # 检查是否是多步骤标题
            is_multi = False
            for multi_title, step_ids in multi_step_titles.items():
                if multi_title in title_lower:
                    for step_id in step_ids:
                        routing[step_id].append(h.title)
                    is_multi = True
                    break
            
            if not is_multi:
                # 单步骤映射
                for step_id, kws in keywords.items():
                    if any(kw in title_lower for kw in kws):
                        routing[step_id].append(h.title)
                        break
        
        return routing
    
    def segment_by_routing(self, content: str, headings: List[Heading], 
                          routing: Dict[str, List[str]], mode: str) -> Dict[str, str]:
        """
        根据路由映射切分原文
        
        核心：直接从原文提取章节内容，不经过 LLM，保证完整性
        """
        # 构建标题到位置和层级的映射
        title_to_heading = {h.title: h for h in headings}
        
        segments = {}
        
        for step_id, titles in routing.items():
            combined_text = []
            
            for title in titles:
                if title == "skip":
                    continue
                    
                heading = title_to_heading.get(title)
                if not heading:
                    logger.warning(f"Title not found: {title}")
                    continue
                
                # 直接从原文提取，100% 完整
                section_text = content[heading.start_pos:heading.end_pos]
                
                # 清理标题标记，保留内容
                lines = section_text.split('\n')
                content_lines = []
                for line in lines:
                    # 跳过标题行（以 # 开头）
                    if not line.startswith('#'):
                        content_lines.append(line)
                
                if content_lines:
                    # 保留原标题作为标记
                    combined_text.append(f"【原文：{title}】\n" + '\n'.join(content_lines).strip())
            
            if combined_text:
                segments[step_id] = "\n\n---\n\n".join(combined_text)
                logger.info(f"Step {step_id}: combined {len(titles)} sections, {len(segments[step_id])} chars")
        
        # 填充空步骤
        segments = self._fill_empty_steps(segments, mode)
        
        return segments
    
    def _fill_empty_steps(self, segments: Dict[str, str], mode: str) -> Dict[str, str]:
        """
        填充空的步骤
        
        策略：
        - QUANT: 7步，如果某步为空，从前一步或后一步复制内容
        - QUAL: 4层，如果某层为空，从相邻层复制内容
        """
        if mode == "quant":
            order = ["1", "2", "3", "4", "5", "6", "7"]
        else:
            order = ["L1", "L2", "L3", "L4"]
        
        for i, step_id in enumerate(order):
            if step_id in segments and segments[step_id].strip():
                continue  # 已有内容，跳过
            
            # 查找前一个有内容的步骤
            prev_content = None
            for j in range(i - 1, -1, -1):
                prev_id = order[j]
                if prev_id in segments and segments[prev_id].strip():
                    prev_content = segments[prev_id]
                    break
            
            # 查找后一个有内容的步骤
            next_content = None
            for j in range(i + 1, len(order)):
                next_id = order[j]
                if next_id in segments and segments[next_id].strip():
                    next_content = segments[next_id]
                    break
            
            # 优先使用前一个步骤的内容（更相关）
            if prev_content:
                segments[step_id] = f"【此部分无独立章节，从相邻部分提取】\n\n{prev_content}"
                logger.info(f"Step {step_id}: filled from previous step")
            elif next_content:
                segments[step_id] = f"【此部分无独立章节，从相邻部分提取】\n\n{next_content}"
                logger.info(f"Step {step_id}: filled from next step")
            else:
                # 没有任何内容可用
                segments[step_id] = "【此部分无内容】"
                logger.warning(f"Step {step_id}: no content available")
        
        return segments
    
    def save_segmented_md(self, output_path: str, segments: Dict[str, str], 
                         source_path: str, mode: str):
        """
        保存为兼容现有格式的 segmented.md
        
        格式兼容旧的 deep_read_pipeline.py 和 social_science_analyzer.py
        """
        lines = [
            "# 论文原文结构化分段（Smart Router）",
            "",
            f"- Source: {source_path}",
            f"- Mode: {mode}",
            f"- Generated: {datetime.now().isoformat()}",
            ""
        ]
        
        # 添加路由映射表（便于调试）
        lines.append("## 路由映射")
        lines.append("")
        
        if mode == "quant":
            order = ["1", "2", "3", "4", "5", "6", "7"]
        else:
            order = ["L1", "L2", "L3", "L4"]
        
        for step_id in order:
            if step_id not in segments:
                continue
            if step_id.startswith('L'):
                step_name = self.QUAL_STEPS.get(step_id, step_id)
            else:
                step_name = self.QUANT_STEPS.get(int(step_id), step_id)
            lines.append(f"- {step_id}: {step_name.split(' - ')[0]}")
        
        lines.append("")
        
        # 按步骤顺序输出内容
        for step_id in order:
            if step_id not in segments:
                continue
            
            if step_id.startswith('L'):
                step_name = self.QUAL_STEPS.get(step_id, step_id)
            else:
                step_name = self.QUANT_STEPS.get(int(step_id), step_id)
            lines.append(f"## {step_id}. {step_name.split(' - ')[0]}")
            lines.append("")
            lines.append("```text")
            lines.append(segments[step_id])
            lines.append("```")
            lines.append("")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        logger.info(f"Saved segmented MD: {output_path}")
    
    def process(self, paddleocr_md_path: str, output_dir: str, mode: str = "auto") -> Tuple[str, str]:
        """
        主处理流程
        
        Returns:
            (output_path, detected_mode)
        """
        os.makedirs(output_dir, exist_ok=True)
        
        # 1. 读取 PaddleOCR MD
        logger.info(f"Reading PaddleOCR MD: {paddleocr_md_path}")
        with open(paddleocr_md_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 2. 提取标题
        headings = self.extract_headings(content)
        logger.info(f"Extracted {len(headings)} headings")
        
        if len(headings) == 0:
            logger.warning("No headings found, treating entire document as single section")
            # 回退：整个文档作为一个部分
            basename = os.path.basename(paddleocr_md_path).replace("_paddleocr.md", "")
            output_path = os.path.join(output_dir, f"{basename}_segmented.md")
            
            # 简单按模式分配
            if mode == "auto":
                mode = "qual"  # 默认 qual
            
            if mode == "quant":
                segments = {"1": content}
            else:
                segments = {"L1": content}
            
            self.save_segmented_md(output_path, segments, paddleocr_md_path, mode)
            return output_path, mode
        
        # 3. LLM 分类
        routing, detected_mode = self.classify_headings(headings, mode)
        logger.info(f"Classification routing: {routing}")
        
        # 4. 根据分类切分原文
        segments = self.segment_by_routing(content, headings, routing, detected_mode)
        
        # 5. 保存兼容格式的输出
        basename = os.path.basename(paddleocr_md_path).replace("_paddleocr.md", "")
        output_path = os.path.join(output_dir, f"{basename}_segmented.md")
        
        self.save_segmented_md(output_path, segments, paddleocr_md_path, detected_mode)
        
        return output_path, detected_mode


def main():
    """CLI 入口"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Smart Segment Router - LLM 分类 + 代码切分")
    parser.add_argument("paddleocr_md_path", help="Path to PaddleOCR extracted markdown")
    parser.add_argument("--out_dir", default="pdf_segmented_md", help="Output directory")
    parser.add_argument("--mode", default="auto", choices=["auto", "quant", "qual"],
                       help="Paper type: auto (detect), quant (7-step), or qual (4-layer)")
    args = parser.parse_args()
    
    if not os.path.exists(args.paddleocr_md_path):
        logger.error(f"File not found: {args.paddleocr_md_path}")
        return 1
    
    router = SmartSegmentRouter()
    output_path, mode = router.process(args.paddleocr_md_path, args.out_dir, args.mode)
    
    print(f"\n[SUCCESS] Segmentation complete!")
    print(f"   Mode: {mode}")
    print(f"   Output: {output_path}")
    
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    exit(main())
