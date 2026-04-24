"""
Prompts Router - Prompt management for all analysis types
"""
import os

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

PROMPT_PATHS = {
    "quant": {
        "step_1": "prompts/quant_analysis/step_1_overview.md",
        "step_2": "prompts/quant_analysis/step_2_theory.md",
        "step_3": "prompts/quant_analysis/step_3_data.md",
        "step_4": "prompts/quant_analysis/step_4_vars.md",
        "step_5": "prompts/quant_analysis/step_5_identification.md",
        "step_6": "prompts/quant_analysis/step_6_results.md",
        "step_7": "prompts/quant_analysis/step_7_critique.md",
    },
    "qual": {
        "L1": "prompts/qual_analysis/L1_Context_Prompt.md",
        "L2": "prompts/qual_analysis/L2_Theory_Prompt.md",
        "L3": "prompts/qual_analysis/L3_Logic_Prompt.md",
        "L4": "prompts/qual_analysis/L4_Value_Prompt.md",
    },
    "long": {
        "overview": "prompts/long/overview.md",
        "theory": "prompts/long/theory.md",
        "methodology": "prompts/long/methodology.md",
        "data_source": "prompts/long/data_source.md",
        "variable_measurement": "prompts/long/variable_measurement.md",
        "identification_assumptions": "prompts/long/identification_assumptions.md",
        "results": "prompts/long/results.md",
        "mechanism": "prompts/long/mechanism.md",
        "robustness": "prompts/long/robustness.md",
        "external_validity": "prompts/long/external_validity.md",
        "contributions_limitations": "prompts/long/contributions_limitations.md",
        "writing_quality": "prompts/long/writing_quality.md",
        "custom": "prompts/long/custom.md",
    },
    "filter": {
        "explorer": "prompts/literature_filter/explorer.md",
        "reviewer": "prompts/literature_filter/reviewer.md",
        "empiricist": "prompts/literature_filter/empiricist.md",
    }
}


class PromptUpdate(BaseModel):
    type: str
    step: str
    content: str


@router.get("/")
async def get_prompt(type: str, step: str):
    """Get prompt content by type and step"""
    if type not in PROMPT_PATHS:
        raise HTTPException(status_code=400, detail=f"Invalid type: {type}")
    
    if step not in PROMPT_PATHS[type]:
        raise HTTPException(status_code=400, detail=f"Invalid step: {step}")
    
    path = os.path.join(BASE_DIR, PROMPT_PATHS[type][step])
    
    if not os.path.exists(path):
        return {"type": type, "step": step, "content": "", "exists": False}
    
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    
    return {"type": type, "step": step, "content": content, "exists": True}


@router.put("/")
async def update_prompt(request: PromptUpdate):
    """Update prompt content"""
    if request.type not in PROMPT_PATHS:
        raise HTTPException(status_code=400, detail=f"Invalid type: {request.type}")
    
    if request.step not in PROMPT_PATHS[request.type]:
        raise HTTPException(status_code=400, detail=f"Invalid step: {request.step}")
    
    path = os.path.join(BASE_DIR, PROMPT_PATHS[request.type][request.step])
    
    # Ensure directory exists
    os.makedirs(os.path.dirname(path), exist_ok=True)
    
    with open(path, "w", encoding="utf-8") as f:
        f.write(request.content)
    
    return {"success": True, "message": "Prompt saved"}


@router.get("/list")
async def list_prompts():
    """List all available prompts"""
    result = {}
    for type_name, steps in PROMPT_PATHS.items():
        result[type_name] = {}
        for step_name, path in steps.items():
            full_path = os.path.join(BASE_DIR, path)
            result[type_name][step_name] = {
                "path": path,
                "exists": os.path.exists(full_path)
            }
    return result
