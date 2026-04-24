"""
Compare Router - AI synthesis for literature comparison
"""
import os
import sys
from typing import Optional, List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

router = APIRouter()


class CompareRequest(BaseModel):
    step: str
    papers: List[str]
    subQuestions: List[str]
    paperData: list
    api_key: Optional[str] = None
    mode: Optional[str] = "single"  # "single" or "multi"


class LongCompareRequest(BaseModel):
    dimension: str
    papers: List[str]
    paperData: list
    api_key: Optional[str] = None
    mode: Optional[str] = "single"  # "single" or "multi"


def get_api_key(provided_key: Optional[str] = None) -> str:
    """Get DeepSeek API key from request or env"""
    if provided_key and provided_key.strip():
        return provided_key.strip()
    return os.environ.get("DEEPSEEK_API_KEY", "")


@router.post("/analyze")
async def analyze_comparison(req: CompareRequest):
    """Generate AI synthesis for 7-step or 4-step comparison - one paragraph style"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com")
        
        # Build prompt - integrated paragraph style
        prompt_parts = []
        prompt_parts.append(f"请将以下文献在「{req.step}」步骤下的回答整合为一段连贯的综述文字。")
        prompt_parts.append("")
        # Determine mode based on number of sub-questions
        mode = req.mode or ("multi" if len(req.subQuestions) > 1 else "single")
        
        # Build prompt based on mode
        if mode == "multi":
            # Multi-sub-question: sectioned format
            prompt_parts = []
            prompt_parts.append(f"请将以下文献在「{req.step}」步骤下的回答整合为一份文献综述。")
            prompt_parts.append("")
            prompt_parts.append("要求：")
            prompt_parts.append("1. 按子问题分节，每节1-3段，每节有明确的主题")
            prompt_parts.append("2. 每节内比较不同文献的观点异同，找出共识与分歧")
            prompt_parts.append("3. 使用间注法引用（作者，年份），例如：(Ludwig et al., 2024)")
            prompt_parts.append("4. 语言简洁、逻辑连贯")
            prompt_parts.append("5. 最后在文末统一附上参考文献目录（按作者姓氏排序）")
            prompt_parts.append("")
            prompt_parts.append("文献内容：")
            
            for paper in req.paperData:
                title = paper.get('title', paper['filename'])
                authors = paper.get('authors', [])
                year = paper.get('year', '年份未知')
                author_str = ', '.join(authors[:2]) if authors else 'Unknown'
                if len(authors) > 2:
                    author_str += ' et al.'
                prompt_parts.append(f"\n--- {title} ({author_str}, {year}) ---")
                for sq, content in paper.get('subQuestions', {}).items():
                    prompt_parts.append(f"【{sq}】")
                    prompt_parts.append(content[:1000])
            
            prompt = "\n".join(prompt_parts)
        else:
            # Single sub-question: integrated paragraph
            prompt_parts = []
            prompt_parts.append(f"请将以下文献在「{req.step}」步骤下的回答整合为一段连贯的综述文字。")
            prompt_parts.append("")
            prompt_parts.append("要求：")
            prompt_parts.append("1. 输出为一段完整的学术性文字，不要分小节、不要加标题、不要写引言")
            prompt_parts.append("2. 比较不同文献的观点异同，找出共识与分歧")
            prompt_parts.append("3. 使用间注法引用（作者，年份），例如：(Ludwig et al., 2024)")
            prompt_parts.append("4. 语言简洁、逻辑连贯，适合作为论文文献综述中的一个段落")
            prompt_parts.append("5. 最后在文末附上参考文献目录（按作者姓氏排序）")
            prompt_parts.append("")
            prompt_parts.append("文献内容：")
            
            for paper in req.paperData:
                title = paper.get('title', paper['filename'])
                authors = paper.get('authors', [])
                year = paper.get('year', '年份未知')
                author_str = ', '.join(authors[:2]) if authors else 'Unknown'
                if len(authors) > 2:
                    author_str += ' et al.'
                prompt_parts.append(f"\n--- {title} ({author_str}, {year}) ---")
                for sq, content in paper.get('subQuestions', {}).items():
                    prompt_parts.append(f"【{sq}】")
                    prompt_parts.append(content[:1000])
            
            prompt = "\n".join(prompt_parts)
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4000
        )
        
        return {"synthesis": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/analyze_long")
async def analyze_long_comparison(req: LongCompareRequest):
    """Generate AI synthesis for long context comparison - one paragraph style"""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com")
        
        # Build prompt based on mode
        mode = req.mode or "single"
        
        if mode == "multi":
            # Multi-dimension: sectioned format
            prompt_parts = []
            prompt_parts.append(f"请将以下文献在「{req.dimension}」维度下的分析整合为一份文献综述。")
            prompt_parts.append("")
            prompt_parts.append("要求：")
            prompt_parts.append("1. 按不同文献分节，每节1-3段，每节有明确的主题")
            prompt_parts.append("2. 每节内比较不同文献的观点异同，找出共识与分歧")
            prompt_parts.append("3. 使用间注法引用（作者，年份），例如：(Ludwig et al., 2024)")
            prompt_parts.append("4. 语言简洁、逻辑连贯")
            prompt_parts.append("5. 最后在文末统一附上参考文献目录（按作者姓氏排序）")
            prompt_parts.append("")
            prompt_parts.append("文献内容：")
            
            for paper in req.paperData:
                title = paper.get('title', paper['filename'])
                authors = paper.get('authors', [])
                year = paper.get('year', '年份未知')
                author_str = ', '.join(authors[:2]) if authors else 'Unknown'
                if len(authors) > 2:
                    author_str += ' et al.'
                prompt_parts.append(f"\n--- {title} ({author_str}, {year}) ---")
                content = paper.get('content', '')[:2000]
                prompt_parts.append(content)
            
            prompt = "\n".join(prompt_parts)
        else:
            # Single dimension: integrated paragraph
            prompt_parts = []
            prompt_parts.append(f"请将以下文献在「{req.dimension}」维度下的分析整合为一段连贯的综述文字。")
            prompt_parts.append("")
            prompt_parts.append("要求：")
            prompt_parts.append("1. 输出为一段完整的学术性文字，不要分小节、不要加标题、不要写引言")
            prompt_parts.append("2. 比较不同文献的观点异同，找出共识与分歧")
            prompt_parts.append("3. 使用间注法引用（作者，年份），例如：(Ludwig et al., 2024)")
            prompt_parts.append("4. 语言简洁、逻辑连贯，适合作为论文文献综述中的一个段落")
            prompt_parts.append("5. 最后在文末附上参考文献目录（按作者姓氏排序）")
            prompt_parts.append("")
            prompt_parts.append("文献内容：")
            
            for paper in req.paperData:
                title = paper.get('title', paper['filename'])
                authors = paper.get('authors', [])
                year = paper.get('year', '年份未知')
                author_str = ', '.join(authors[:2]) if authors else 'Unknown'
                if len(authors) > 2:
                    author_str += ' et al.'
                prompt_parts.append(f"\n--- {title} ({author_str}, {year}) ---")
                content = paper.get('content', '')[:2000]
                prompt_parts.append(content)
            
            prompt = "\n".join(prompt_parts)
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=4000
        )
        
        return {"synthesis": response.choices[0].message.content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
