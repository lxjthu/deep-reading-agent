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


class LongCompareRequest(BaseModel):
    dimension: str
    papers: List[str]
    paperData: list
    api_key: Optional[str] = None


def get_api_key(provided_key: Optional[str] = None) -> str:
    """Get DeepSeek API key from request or env"""
    if provided_key and provided_key.strip():
        return provided_key.strip()
    return os.environ.get("DEEPSEEK_API_KEY", "")


@router.post("/analyze")
async def analyze_comparison(req: CompareRequest):
    """Generate AI synthesis for 7-step or 4-step comparison"""
    try:
        from openai import OpenAI
        api_key = get_api_key()
        if not api_key:
            # Try to use user's key from request if available
            # For now, fallback to env
            pass
        
        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com")
        
        # Build prompt
        prompt_parts = [f"请基于以下文献在「{req.step}」下的回答，生成一份文献综述。"]
        prompt_parts.append("要求：")
        prompt_parts.append("1. 比较不同文献的观点异同")
        prompt_parts.append("2. 指出共识和分歧")
        prompt_parts.append("3. 使用间注法引用（作者，年份）")
        prompt_parts.append("4. 最后附上参考文献目录")
        prompt_parts.append("")
        prompt_parts.append("文献内容：")
        
        for paper in req.paperData:
            prompt_parts.append(f"\n--- {paper.get('title', paper['filename'])} ---")
            for sq, content in paper.get('subQuestions', {}).items():
                prompt_parts.append(f"【{sq}】")
                prompt_parts.append(content[:1000])  # Limit content length
        
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
    """Generate AI synthesis for long context comparison"""
    try:
        from openai import OpenAI
        api_key = get_api_key()
        client = OpenAI(api_key=get_api_key(req.api_key), base_url="https://api.deepseek.com")
        
        # Build prompt
        prompt_parts = [f"请基于以下文献在「{req.dimension}」维度下的分析，生成一份文献综述。"]
        prompt_parts.append("要求：")
        prompt_parts.append("1. 比较不同文献的观点异同")
        prompt_parts.append("2. 指出共识和分歧")
        prompt_parts.append("3. 使用间注法引用（作者，年份）")
        prompt_parts.append("4. 最后附上参考文献目录")
        prompt_parts.append("")
        prompt_parts.append("文献内容：")
        
        for paper in req.paperData:
            prompt_parts.append(f"\n--- {paper.get('title', paper['filename'])} ---")
            prompt_parts.append(paper.get('content', '')[:1500])  # Limit content length
        
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
