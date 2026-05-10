import json
import re
from typing import Optional


class ParseError(Exception):
    pass


def parse_dimension_document(text: str) -> dict:
    result: dict = {
        "template_name": "",
        "description": "",
        "dimensions": [],
    }

    lines = text.split("\n")
    current_dim: Optional[dict] = None
    in_code_block = False
    code_lines: list[str] = []

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("# ") and not result["template_name"]:
            result["template_name"] = stripped[2:].strip()

        elif stripped.startswith("> ") and not result["description"]:
            result["description"] = stripped[2:].strip()

        elif stripped.startswith("## "):
            if current_dim and not in_code_block:
                if code_lines:
                    current_dim["prompt_content"] = "\n".join(code_lines)
                    code_lines = []
                result["dimensions"].append(current_dim)

            dim_title = stripped[3:].strip()
            if "\uff1a" in dim_title or ":" in dim_title:
                parts = re.split(r"[\uff1a:]", dim_title, 1)
                name = parts[1].strip() if len(parts) > 1 else dim_title
            else:
                name = dim_title

            current_dim = {
                "dim_name": name,
                "description": "",
                "default_question": "",
                "prompt_content": "",
                "group_name": "核心维度",
            }

        elif current_dim and not in_code_block:
            if re.match(r"\*\*\u63cf\u8ff0[\uff1a:]\*\*", stripped):
                current_dim["description"] = re.sub(r"\*\*\u63cf\u8ff0[\uff1a:]\*\*\s*", "", stripped)
            elif re.match(r"\*\*\u9ed8\u8ba4\u95ee\u9898[\uff1a:]\*\*", stripped):
                current_dim["default_question"] = re.sub(r"\*\*\u9ed8\u8ba4\u95ee\u9898[\uff1a:]\*\*\s*", "", stripped)

        if stripped.startswith("```"):
            if in_code_block:
                if current_dim:
                    current_dim["prompt_content"] = "\n".join(code_lines)
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
        elif in_code_block and current_dim:
            code_lines.append(line)

    if current_dim and not in_code_block:
        if code_lines:
            current_dim["prompt_content"] = "\n".join(code_lines)
        result["dimensions"].append(current_dim)

    if not result["template_name"]:
        raise ParseError("未找到模板标题（应以 # 开头）")
    if len(result["dimensions"]) == 0:
        raise ParseError("未识别到任何维度（应以 ## 维度 N：开头）")

    return result


def parse_json_document(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ParseError(f"JSON 解析失败: {e}")

    if "dimensions" not in data:
        raise ParseError("JSON 缺少 dimensions 字段")
    return data


def parse_document(text: str, file_extension: str = ".txt") -> dict:
    ext = file_extension.lower()
    if ext in (".json",):
        return parse_json_document(text)
    elif ext in (".txt", ".md", ".markdown", ""):
        return parse_dimension_document(text)
    else:
        raise ParseError(f"不支持的文件格式: {file_extension}")
