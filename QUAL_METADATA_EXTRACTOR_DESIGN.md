# QUAL 论文元数据提取方案

**创建时间**: 2026-02-03
**版本**: v1.0
**状态**: 待实现

---

## 设计目标

为 QUAL 论文（社会科学 4 层金字塔分析）开发元数据提取工具，采用两次提取逻辑：

### 两次提取逻辑概览

```
┌─────────────────────────────────────────────────────────────────┐
│  第一次提取：从生成的 MD 报告中提取                           │
│  输入：L1_Context.md, L2_Theory.md, L3_Logic.md, L4_Value.md     │
│  提取目标：## 数字. 标题 格式的小标题 + 30字中文总结           │
│  工具：正则表达式提取 + DeepSeek 30字总结                       │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│  第二次提取：从原始 PDF 文件中提取                             │
│  输入：原始 PDF 文件                                            │
│  提取目标：第1-2页的作者、标题、期刊、年份                       │
│  工具：Qwen-vl-plus 视觉模型 + pymupdf                         │
└────────────────────┬────────────────────────────────────────────┘
                     │
                     ↓
┌─────────────────────────────────────────────────────────────────┐
│  元数据合并与注入                                               │
│  PDF 元数据优先覆盖 MD 元数据                                  │
│  生成 YAML Frontmatter 并注入到各层文件                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## 第一次提取：从 MD 报告中提取

### 1.1 提取目标

从生成的 4 层分析报告中提取结构化元数据：

| 层级 | 文件 | 提取的 `## 数字. 标题` 部分 |
|------|------|---------------------------|
| L1 | L1_Context.md | `## 1. 论文分类`, `## 2. 核心问题`, `## 3. 政策文件`, `## 4. 现状数据`, `## 5. 理论重要性`, `## 6. 实践重要性`, `## 7. 关键文献` |
| L2 | L2_Theory.md | `## 1. 经典理论回顾`, `## 2. 核心构念`, `## 3. 构念关系`, `## 4. 理论框架`, `## 5. 理论贡献`, `## 6. 详细分析` |
| L3 | L3_Logic.md | 根据体裁不同，提取不同的 `## 数字. 标题`（见下文） |
| L4 | L4_Value.md | `## 1. 研究缺口`, `## 2. 学术贡献`, `## 3. 实践启示`, `## 4. 价值定位`, `## 5. 详细分析`, `## 6. 未来展望`（可选）|

### 1.2 L3 层的体裁适配格式

**Theoretical (理论构建)** - 11 部分：
```markdown
## 1. 研究体裁
## 2. 逻辑类型
## 3. 核心问题
## 4. 概念体系
## 5. 逻辑推演
## 6. 模型构建
## 7. 命题提出
## 8. 理论贡献
## 9. 应用价值
## 10. 理论依据
## 11. 详细分析
```

**Case Study (案例研究)** - 11 部分：
```markdown
## 1. 研究体裁
## 2. 逻辑类型
## 3. 核心问题
## 4. 关键阶段
## 5. 整体流程
## 6. 相互作用
## 7. 因果关系
## 8. 关键节点
## 9. 证据支撑
## 10. 验证结果
## 11. 详细分析
```

**QCA (定性比较分析)** - 11 部分：
```markdown
## 1. 研究体裁
## 2. 逻辑类型
## 3. 核心问题
## 4. 因果路径
## 5. 条件组合
## 6. 组间比较
## 7. 路径效应
## 8. 统计证据
## 9. 验证方法
## 10. 验证结果
## 11. 详细分析
```

**Quantitative (定量研究)** - 11 部分：
```markdown
## 1. 研究体裁
## 2. 逻辑类型
## 3. 核心问题
## 4. 研究假设
## 5. 变量关系
## 6. 模型设定
## 7. 回归结果
## 8. 统计显著性
## 9. 稳健性检验
## 10. 验证结果
## 11. 详细分析
```

**Review (文献综述)** - 11 部分：
```markdown
## 1. 研究体裁
## 2. 逻辑类型
## 3. 核心问题
## 4. 整合框架
## 5. 理论谱系
## 6. 演进阶段
## 7. 跨域对话
## 8. 发展趋势
## 9. 未来方向
## 10. 文献依据
## 11. 详细分析
```

### 1.3 提取逻辑

**步骤 1：正则提取小标题**
```python
def extract_sections_from_markdown(md_content: str) -> dict:
    """
    从 QUAL 分析的 Markdown 中提取 `## 数字. 标题` 格式的章节
    
    Returns:
        {
            "1. 论文分类": "完整内容...",
            "2. 核心问题": "完整内容...",
            ...
        }
    """
    sections = {}
    current_num = None
    current_title = None
    current_content = []
    
    for line in md_content.split('\n'):
        # 匹配 ## 数字. 标题
        match = re.match(r'^##\s+(\d+)\.\s+(.+)$', line)
        if match:
            # 保存上一个章节
            if current_num and current_title:
                key = f"{current_num}. {current_title}"
                sections[key] = '\n'.join(current_content).strip()
            
            # 开始新章节
            current_num = match.group(1)
            current_title = match.group(2).strip()
            current_content = []
        elif line.startswith('#'):
            # 遇到其他标题，跳过
            continue
        else:
            if current_num and current_title:
                current_content.append(line)
    
    # 保存最后一个章节
    if current_num and current_title:
        key = f"{current_num}. {current_title}"
        sections[key] = '\n'.join(current_content).strip()
    
    return sections
```

**步骤 2：DeepSeek 30 字总结**
```python
def summarize_section_with_deepseek(client, title: str, content: str) -> str:
    """
    用 DeepSeek 将章节内容总结为 30 字中文
    
    Args:
        client: DeepSeek 客户端
        title: 章节标题（如 "1. 论文分类"）
        content: 章节完整内容
    
    Returns:
        30 字以内的中文摘要
    """
    if len(content) < 50:
        return content[:30]  # 内容太短，直接截取
    
    prompt = f"""请将以下内容总结为30字以内的一句话：
标题：{title}
内容：{content}

要求：
- 中文输出
- 30字以内
- 抓住核心要点
"""
    
    try:
        resp = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个精确的学术内容总结专家。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=100
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Summary failed for {title}: {e}")
        return content[:30]  # 降级：截取前30字
```

**步骤 3：批量处理所有章节**
```python
def extract_all_layer_subsections(layer_outputs: dict, deepseek_client) -> dict:
    """
    提取所有层的子章节元数据
    
    Args:
        layer_outputs: {
            "L1_Context": "markdown content",
            "L2_Theory": "markdown content",
            "L3_Logic": "markdown content",
            "L4_Value": "markdown content"
        }
        deepseek_client: DeepSeek 客户端
    
    Returns:
        {
            "L1_Context": {
                "1. 论文分类": "30字摘要",
                "2. 核心问题": "30字摘要",
                ...
            },
            "L2_Theory": {...},
            "L3_Logic": {...},
            "L4_Value": {...}
        }
    """
    all_metadata = {}
    
    for layer_name, md_content in layer_outputs.items():
        # 提取章节
        sections = extract_sections_from_markdown(md_content)
        
        # 总结每个章节
        subsections_meta = {}
        for title, content in sections.items():
            if len(content) >= 50:  # 仅总结足够长的章节
                summary = summarize_section_with_deepseek(deepseek_client, title, content)
                subsections_meta[title] = summary
        
        all_metadata[layer_name] = subsections_meta
        logger.info(f"Extracted {len(subsections_meta)} subsections from {layer_name}")
    
    return all_metadata
```

### 1.4 输出示例

```python
{
    "L1_Context": {
        "1. 论文分类": "本文为理论构建研究，构建类ChatGPT技术赋能乡村文化振兴的分析框架。",
        "2. 核心问题": "探究生成式AI技术为乡村文化振兴带来的机遇、挑战及实现路径。",
        "3. 政策文件": "党的二十大报告提出精细化服务理念，为AI技术赋能乡村文化提供政策指引。",
        "4. 现状数据": "ChatGPT月活破亿，算力消耗3640PF-days，凸显数字基础设施与算力鸿沟挑战。",
        "5. 理论重要性": "拓展数字社会学在乡村研究的应用，为乡村文化理论注入科技维度。",
        "6. 实践重要性": "为政府部门制定AI赋能乡村文化政策、基层实践者应用技术提供决策参考。",
        "7. 关键文献": "文献分析了技术特性、乡村现状、数据质量、AI艺术创作、算力成本及意识形态风险。"
    },
    "L2_Theory": {
        "1. 经典理论回顾": "回顾公共产品理论、技术接受模型、社会嵌入理论、知识社会学，分析技术赋能机制。",
        "2. 核心构念": "定义类ChatGPT、乡村文化振兴、赋能、技术接受度、文化主体性等5个核心概念。",
        "3. 构念关系": "梳理技术对乡村文化的赋能关系、制约条件对赋能效果的影响等4种构念关系。",
        "4. 理论框架": "构建技术赋能-条件约束-风险反思三维框架，系统分析技术赋能的完整过程。",
        "5. 理论贡献": "提出技术赋能文化主体性悖论、数据殖民与文化安全关切，拓展技术社会学研究边界。",
        "6. 详细分析": "通过多理论融合、构念定义精确、逻辑关系严密、框架创新性强，体现社会科学深度。"
    },
    "L3_Logic": {
        "1. 研究体裁": "Theoretical",
        "2. 逻辑类型": "理论逻辑",
        "3. 核心问题": "探究技术如何在特定乡村场域中实现文化赋能潜力，以及如何系统性化解张力。",
        "4. 概念体系": "包含驱动要素（技术赋能）、制约条件（基础设施、主体能力等）、整合方案（基建-主体-技术-制度）。",
        "5. 逻辑推演": "遵循理想模型推演（技术机遇）→现实约束分析（挑战）→系统性整合方案（路径）。",
        "6. 模型构建": "构建技术赋能-风险制约-系统整合模型，包含技术内核、机制层、约束层、整合层。",
        "7. 命题提出": "技术赋能有效性取决于社会技术条件匹配度；生成式AI内含提升效率与削弱主体性张力。",
        "8. 理论贡献": "将生成式AI与乡村文化振兴深度耦合，构建涵盖机遇-挑战的完整分析框架。",
        "9. 应用价值": "为政府、基层实践者、科技企业、政策制定者提供结构化问题诊断框架和行动路线图。",
        "10. 理论依据": "建立在技术的社会建构论、创新扩散理论、赋权理论、治理理论、文化政治经济学之上。",
        "11. 详细分析": "机制核心是技术如何在条件受限的乡村场域实现文化赋能潜力，通过社会技术系统协同演进实现目标。"
    },
    "L4_Value": {
        "1. 研究缺口": "现有研究缺乏对生成式AI与乡村文化交叉领域的理论探讨和系统分析框架。",
        "2. 学术贡献": "构建技术-主体-产业-制度整合分析框架，将主体性保障提升到与技术同等重要位置。",
        "3. 实践启示": "提出基建与人才政策、人才与采购政策、研发与数据政策、法律与监管政策等具体建议。",
        "4. 价值定位": "兼具前瞻性、系统性和务实性，提供中观分析框架和清晰行动清单。",
        "5. 详细分析": "完成从机遇识别到挑战剖析再到路径构建的完整、冷静的战略思考，平衡理论前瞻与实践指导。"
    }
}
```

---

## 第二次提取：从 PDF 文件中提取

### 2.1 提取目标

从原始 PDF 文件中提取基础元数据：

| 字段 | 说明 | 来源 |
|------|------|------|
| title | 论文完整标题 | PDF 第 1 页顶部 |
| authors | 所有作者列表 | PDF 第 1 页顶部 |
| journal | 发表期刊全名 | PDF 第 1-2 页页眉 |
| year | 发表年份（4位数字） | PDF 第 1-2 页页眉 |

### 2.2 实现逻辑（复用现有代码）

**步骤 1：PDF 转图片**
```python
def convert_pdf_to_images(pdf_path: str, max_pages: int = 2) -> list:
    """
    将 PDF 前几页转换为图片（base64）
    
    Args:
        pdf_path: PDF 文件路径
        max_pages: 转换的最大页数（默认 2）
    
    Returns:
        [base64_image1, base64_image2, ...]
    """
    if not pymupdf:
        logger.warning("pymupdf not available")
        return []
    
    doc = pymupdf.open(pdf_path)
    images = []
    
    for page_num in range(min(max_pages, len(doc))):
        page = doc.load_page(page_num)
        mat = pymupdf.Matrix(pymupdf.Identity)
        pix = page.get_pixmap(matrix=mat, dpi=200)
        
        img_bytes = pix.tobytes("png")
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        images.append(img_base64)
    
    doc.close()
    logger.info(f"Converted {len(images)} PDF pages to images")
    return images
```

**步骤 2：Qwen-vl-plus 视觉提取**
```python
def extract_pdf_metadata_with_qwen(images: list) -> dict:
    """
    用 Qwen-vl-plus 从 PDF 图片中提取元数据
    
    Args:
        images: PDF 图片列表（base64）
    
    Returns:
        {
            "title": "论文标题",
            "authors": ["作者1", "作者2"],
            "journal": "期刊名称",
            "year": "2024"
        }
    """
    qwen_api_key = os.getenv("QWEN_API_KEY")
    if not qwen_api_key:
        logger.warning("QWEN_API_KEY not found")
        return {"title": "Unknown", "authors": ["Unknown"], "journal": "Unknown", "year": "Unknown"}
    
    client = OpenAI(
        api_key=qwen_api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    
    prompt = """请从以下论文图片中提取以下元数据：
1. 论文标题（完整）
2. 作者列表（所有作者，用逗号分隔）
3. 发表期刊（期刊全名）
4. 发表年份（仅4位数字）

请以 JSON 格式返回：
{
    "title": "...",
    "authors": ["...", "..."],
    "journal": "...",
    "year": "..."
}

注意：
- 期刊名称和年份通常在页面顶部的页眉
- 仔细识别页眉位置的期刊名和年份
"""
    
    try:
        content_messages = [{"type": "text", "text": prompt}]
        
        for img_base64 in images:
            content_messages.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{img_base64}"}
            })
        
        logger.info(f"Sending request to Qwen VL with {len(images)} images...")
        
        resp = client.chat.completions.create(
            model="qwen-vl-plus",
            messages=[
                {"role": "system", "content": "你是专业的学术论文元数据提取专家。"},
                {"role": "user", "content": content_messages}
            ],
            temperature=0.0
        )
        
        response_content = resp.choices[0].message.content
        
        # 提取 JSON
        if "```json" in response_content:
            start_idx = response_content.find("```json") + 7
            end_idx = response_content.find("```", start_idx)
            json_str = response_content[start_idx:end_idx].strip()
        elif "```" in response_content:
            start_idx = response_content.find("```") + 3
            end_idx = response_content.find("```", start_idx)
            json_str = response_content[start_idx:end_idx].strip()
        else:
            json_str = response_content.strip()
        
        result = json.loads(json_str)
        logger.info(f"Successfully extracted PDF metadata: {result.get('title', 'Unknown')[:50]}...")
        return result
        
    except Exception as e:
        logger.error(f"Qwen VL extraction failed: {e}")
        return {
            "title": "Unknown",
            "authors": ["Unknown"],
            "journal": "Unknown",
            "year": "Unknown"
        }
```

### 2.3 输出示例

```python
{
    "title": "类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径",
    "authors": ["张三", "李四", "王五"],
    "journal": "中国软科学",
    "year": "2024"
}
```

---

## 元数据合并与注入

### 3.1 合并策略

```python
def merge_metadata(subsections_meta: dict, pdf_metadata: dict) -> dict:
    """
    合并两次提取的元数据
    
    Args:
        subsections_meta: 第一次提取的结果（从 MD）
        pdf_metadata: 第二次提取的结果（从 PDF）
    
    Returns:
        合并后的完整元数据
    """
    merged = {
        # PDF 元数据（基础元数据）
        "title": pdf_metadata.get("title", ""),
        "authors": pdf_metadata.get("authors", []),
        "journal": pdf_metadata.get("journal", ""),
        "year": pdf_metadata.get("year", ""),
        
        # 标签
        "tags": ["paper", "qual", "deep-reading"]
    }
    
    # 添加子章节摘要
    for layer_name, subsections in subsections_meta.items():
        merged[f"{layer_name}_subsections"] = subsections
    
    return merged
```

### 3.2 注入 Frontmatter

```python
def inject_qual_frontmatter(md_content: str, metadata: dict) -> str:
    """
    为 QUAL 分析文件注入 YAML Frontmatter
    
    Args:
        md_content: 原始 Markdown 内容
        metadata: 元数据字典
    
    Returns:
        注入后的 Markdown 内容
    """
    # 解析现有 frontmatter
    existing_meta = {}
    body_content = md_content
    
    if md_content.startswith("---\n"):
        end_idx = md_content.find("\n---\n", 4)
        if end_idx != -1:
            try:
                import yaml
                fm_str = md_content[4:end_idx]
                existing_meta = yaml.safe_load(fm_str) or {}
                body_content = md_content[end_idx + 5:]
            except Exception as e:
                logger.warning(f"Failed to parse existing frontmatter: {e}")
    
    # 合并元数据（新元数据优先）
    merged_meta = existing_meta.copy()
    merged_meta.update(metadata)
    
    # 生成 YAML Frontmatter
    import yaml
    yaml_str = yaml.safe_dump(merged_meta, allow_unicode=True, sort_keys=False).strip()
    frontmatter_block = f"---\n{yaml_str}\n---\n\n"
    
    return frontmatter_block + body_content
```

### 3.3 添加导航链接

```python
def add_qual_navigation_links(md_content: str, layer: str, all_layers: list) -> str:
    """
    为 QUAL 分析文件添加导航链接
    
    Args:
        md_content: Markdown 内容
        layer: 当前层级（如 "L1_Context"）
        all_layers: 所有层级列表 ["L1_Context", "L2_Theory", "L3_Logic", "L4_Value"]
    
    Returns:
        添加导航后的内容
    """
    # 检查是否已有导航
    if "## 导航" in md_content or "## Navigation" in md_content:
        return md_content
    
    # 生成导航段落
    navigation = "\n\n## 导航\n\n"
    
    # 链接到总报告
    full_report_name = "Full_Report"  # 或从文件名推断
    navigation += f"**返回总报告**：[[{full_report_name}]]\n\n"
    
    # 链接到其他层级
    other_layers = [l for l in all_layers if l != layer]
    if other_layers:
        navigation += "**其他层级**：\n"
        for l in other_layers:
            navigation += f"- [[{l}]]\n"
    
    return md_content + navigation
```

---

## 完整工作流程

### 4.1 主流程

```python
def extract_qual_metadata(paper_dir: str, output_dir: str, pdf_dir: str):
    """
    完整的 QUAL 元数据提取流程
    
    Args:
        paper_dir: 论文输出目录（包含 L1_Context.md 等）
        output_dir: 输出目录（可选，默认覆盖原文件）
        pdf_dir: PDF 文件目录
    """
    # 1. 加载所有层级的 Markdown 内容
    layer_outputs = {}
    for layer in ["L1_Context", "L2_Theory", "L3_Logic", "L4_Value"]:
        layer_file = os.path.join(paper_dir, f"{layer}.md")
        if os.path.exists(layer_file):
            with open(layer_file, 'r', encoding='utf-8') as f:
                layer_outputs[layer] = f.read()
    
    if not layer_outputs:
        logger.error("No layer files found")
        return
    
    logger.info(f"Loaded {len(layer_outputs)} layer files")
    
    # 2. 第一次提取：从 MD 中提取子章节（DeepSeek 30字总结）
    deepseek_client = get_deepseek_client()
    if not deepseek_client:
        logger.error("DeepSeek client not available")
        return
    
    logger.info("Starting Step 1: Extract subsections from MD (DeepSeek summary)...")
    subsections_meta = extract_all_layer_subsections(layer_outputs, deepseek_client)
    
    # 3. 第二次提取：从 PDF 中提取基础元数据
    pdf_path = find_pdf_for_paper(pdf_dir, paper_dir)
    if not pdf_path:
        logger.warning(f"No PDF found for paper in {pdf_dir}")
        pdf_metadata = {}
    else:
        logger.info(f"Starting Step 2: Extract metadata from PDF ({pdf_path})...")
        images = convert_pdf_to_images(pdf_path, max_pages=2)
        if images:
            pdf_metadata = extract_pdf_metadata_with_qwen(images)
        else:
            pdf_metadata = {}
    
    # 4. 合并元数据
    logger.info("Merging metadata...")
    merged_metadata = merge_metadata(subsections_meta, pdf_metadata)
    
    # 5. 注入 Frontmatter 和导航链接
    all_layers = ["L1_Context", "L2_Theory", "L3_Logic", "L4_Value"]
    
    for layer in all_layers:
        if layer in layer_outputs:
            layer_file = os.path.join(paper_dir, f"{layer}.md")
            
            with open(layer_file, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # 注入 Frontmatter
            new_content = inject_qual_frontmatter(content, merged_metadata)
            
            # 添加导航链接
            new_content = add_qual_navigation_links(new_content, layer, all_layers)
            
            # 保存（覆盖原文件）
            with open(layer_file, 'w', encoding='utf-8') as f:
                f.write(new_content)
            
            logger.info(f"Updated {layer} with frontmatter and navigation")
    
    logger.info("QUAL metadata extraction complete!")
```

### 4.2 查找对应 PDF

```python
def find_pdf_for_paper(pdf_dir: str, paper_dir: str) -> str:
    """
    根据论文目录名称查找对应的 PDF 文件
    
    Args:
        pdf_dir: PDF 根目录
        paper_dir: 论文输出目录（如 "social_science_results_v2/类ChatGPT..."）
    
    Returns:
        PDF 文件路径，未找到返回 None
    """
    # 从目录名提取论文名称
    paper_name = os.path.basename(paper_dir)
    
    # 尝试匹配 PDF
    for root, dirs, files in os.walk(pdf_dir):
        for file in files:
            if file.endswith('.pdf'):
                # 移除 .pdf 后缀后比较
                pdf_basename = os.path.splitext(file)[0]
                if pdf_basename in paper_name or paper_name in pdf_basename:
                    pdf_path = os.path.join(root, file)
                    logger.info(f"Found PDF: {pdf_path}")
                    return pdf_path
    
    logger.warning(f"No PDF found for paper: {paper_name}")
    return None
```

---

## 文件结构

### 5.1 新文件

```
qual_metadata_extractor/
├── __init__.py
├── extractor.py              # 主提取逻辑
├── md_extractor.py           # MD 提取（第一次提取）
├── pdf_extractor.py          # PDF 提取（第二次提取）
├── merger.py                 # 元数据合并
└── injector.py               # Frontmatter 注入
```

### 5.2 使用示例

```python
from qual_metadata_extractor.extractor import extract_qual_metadata

# 提取单个论文
extract_qual_metadata(
    paper_dir="social_science_results_v2/类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径",
    output_dir="social_science_results_v2",  # 可选，默认覆盖
    pdf_dir="E:\\pdf\\001"
)
```

---

## 环境变量要求

```env
DEEPSEEK_API_KEY=sk-your-deepseek-key    # 用于 DeepSeek 30字总结
QWEN_API_KEY=sk-your-qwen-key           # 用于 PDF 视觉提取
```

---

## 输出示例

### 注入后的 L1_Context.md

```markdown
---
title: 类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径
authors:
- 张三
- 李四
- 王五
journal: 中国软科学
year: '2024'
tags:
- paper
- qual
- deep-reading
L1_Context_subsections:
  "1. 论文分类": 本文为理论构建研究，构建类ChatGPT技术赋能乡村文化振兴的分析框架。
  "2. 核心问题": 探究生成式AI技术为乡村文化振兴带来的机遇、挑战及实现路径。
  "3. 政策文件": 党的二十大报告提出精细化服务理念，为AI技术赋能乡村文化提供政策指引。
  "4. 现状数据": ChatGPT月活破亿，算力消耗3640PF-days，凸显数字基础设施与算力鸿沟挑战。
  "5. 理论重要性": 拓展数字社会学在乡村研究的应用，为乡村文化理论注入科技维度。
  "6. 实践重要性": 为政府部门、基层实践者提供AI赋能乡村文化的决策参考和行动指南。
  "7. 关键文献": 文献分析了技术特性、乡村现状、数据质量、AI艺术创作、算力成本及意识形态风险。
---

## 1. 论文分类
**Theoretical** (理论构建)...

## 2. 核心问题
本文旨在系统探究...

## 导航

**返回总报告**：[[Full_Report]]

**其他层级**：
- [[L2_Theory]]
- [[L3_Logic]]
- [[L4_Value]]
```

---

## 关键差异对比

| 维度 | QUANT 提取 | QUAL 提取 |
|------|-----------|----------|
| **标题格式** | `### 标题`（三级标题） | `## 数字. 标题`（二级标题+数字） |
| **提取内容** | 步骤文件（1-7_*.md） | 层级文件（L1-L4.md） |
| **总结长度** | 30字 | 30-50字（QUAL 内容更丰富） |
| **L3 格式** | 固定 7 部分 | 根据体裁动态 11 部分 |
| **PDF 提取** | 复用现有逻辑 | 复用现有逻辑 |
| **导航链接** | 链接到 Final_Report | 链接到 Full_Report + 其他层级 |

---

## 下一步

1. ✅ 方案确认
2. ⏳ 实现 `qual_metadata_extractor/` 模块
3. ⏳ 测试提取效果
4. ⏳ 集成到批量流水线
5. ⏳ 性能优化（并发提取、缓存）

---

**文档维护者**: Deep Reading Agent Team
**最后更新**: 2026-02-03
