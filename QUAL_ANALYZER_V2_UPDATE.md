# QUAL 分析器 v2.0 更新说明

**更新日期**: 2026-02-03
**版本**: v2.0 (Markdown 格式输出)
**状态**: ✅ 测试通过

---

## 核心变更

### 1. 从 JSON 输出改为 Markdown 输出

**旧方案 (v1)**:
```python
# 使用 json_repair 解析 LLM 输出
result = json_repair.repair_json(content, return_objects=True)
data = result.get("policy_context", [])
```

**新方案 (v2)**:
```python
# 直接使用 Markdown 输出
markdown_content = response.choices[0].message.content
# 无需解析，直接保存
```

### 2. 动态加载外部提示词文件

**新功能**:
```python
def _load_prompt_from_file(self, layer: str) -> str:
    """从 prompts/qual_analysis/ 目录加载提示词"""
    prompt_file = f"prompts/qual_analysis/{layer}_Prompt.md"
    with open(prompt_file, 'r', encoding='utf-8') as f:
        return f.read()
```

**支持的提示词文件**:
- `prompts/qual_analysis/L1_Context_Prompt.md`
- `prompts/qual_analysis/L2_Theory_Prompt.md`
- `prompts/qual_analysis/L3_Logic_Prompt.md`
- `prompts/qual_analysis/L4_Value_Prompt.md`

### 3. L3 层体裁自适应

**新功能**:
```python
# 从 L1 输出中提取体裁
genre = analyzer._extract_genre_from_l1_markdown(l1_markdown)

# L3 根据体裁调整输出格式
l3_markdown = analyzer.analyze_l3_logic(text_l3, genre=genre)
```

**支持的体裁**:
- **Theoretical**: 理论构建 (概念体系、逻辑推演、模型构建、命题提出...)
- **Case Study**: 案例研究 (关键阶段、整体流程、相互作用、因果关系...)
- **QCA**: 定性比较分析 (因果路径、条件组合、组间比较、路径效应...)
- **Quantitative**: 定量研究 (研究假设、变量关系、模型设定、回归结果...)
- **Review**: 文献综述 (整合框架、理论谱系、演进阶段、跨域对话...)

### 4. 直接保存 Markdown

**旧方案 (v1)**:
```python
# 从 JSON 生成 Markdown
analyzer.generate_markdown(l1_res, "L1_Context", basename, paper_out_dir)
```

**新方案 (v2)**:
```python
# 直接保存 LLM 输出的 Markdown
analyzer.save_layer_markdown(l1_markdown, "L1_Context", basename, paper_out_dir)
```

---

## 文件对比

### 主要文件变化

| 文件 | 说明 |
|------|------|
| `social_science_analyzer.py` | v1 版本 (JSON 输出，已备份为 v1_backup) |
| `social_science_analyzer_v2.py` | **v2 版本 (Markdown 输出)** ✅ 新版本 |
| `prompts/qual_analysis/*_Prompt.md` | 提示词文件 (4个层级) |

### 新增功能

| 功能 | 代码位置 | 说明 |
|------|---------|------|
| 动态提示词加载 | `_load_prompt_from_file()` | 从外部文件加载提示词 |
| Markdown LLM 调用 | `_call_llm_markdown()` | 直接返回 Markdown，无需 JSON |
| 体裁提取 | `_extract_genre_from_l1_markdown()` | 从 L1 输出中提取体裁 |
| L3 体裁自适应 | `analyze_l3_logic()` | 根据体裁调整输出格式 |
| 简化保存方法 | `save_layer_markdown()` | 直接保存 Markdown |
| 总报告生成 | `generate_full_report()` | 合并 4 层为完整报告 |

---

## 使用方法

### 命令行调用

```bash
# 激活虚拟环境
.\venv\Scripts\Activate.ps1

# 单个文件测试
python social_science_analyzer_v2.py "test_segmented" --filter "类ChatGPT"

# 批量处理整个目录
python social_science_analyzer_v2.py "pdf_segmented_md"

# 指定输出目录
python social_science_analyzer_v2.py "pdf_segmented_md" --out_dir "my_results"
```

### 输出结构

```
social_science_results_v2/
└── 论文名称/
    ├── L1_Context.md         # 第1层：背景层分析
    ├── L2_Theory.md          # 第2层：理论层分析
    ├── L3_Logic.md           # 第3层：逻辑层分析
    ├── L4_Value.md           # 第4层：价值层分析
    └── 论文名称_Full_Report.md  # 总报告
```

---

## 输出格式示例

### L1_Context.md

```markdown
## 1. 论文分类
**Theoretical** (理论构建)...

## 2. 核心问题
本文旨在系统探究...

## 3. 政策文件
- **name**: 党的二十大报告
- **year**: 2022
- **level**: Central
- **content**: 明确提出"精细化服务"理念...

## 4. 现状数据
- **item**: ChatGPT月活跃用户数
- **value**: 破亿
- **unit**: 人
- **context**: ChatGPT推出仅两个月后达到...

## 5. 理论重要性
本研究的理论意义重大...

## 6. 实践重要性
本研究的实践意义直接指向...

## 7. 关键文献
- **authors**: [文献4的作者]
- **year**: [文献4的年份]
- **key_insights**: 该文献将ChatGPT理解为...
```

### L3_Logic.md (Theoretical 格式)

```markdown
## 1. 研究体裁
Theoretical

## 2. 逻辑类型
理论逻辑

## 3. 核心问题
本论文试图解决的核心机制问题是...

## 4. 概念体系
论文构建了一个由核心驱动要素...

## 5. 逻辑推演
论文的理论构建遵循一个辩证的...

## 6. 模型构建
论文构建了一个"技术赋能-风险制约-系统整合"...

## 7. 命题提出
基于上述模型，论文隐含地提出了一系列...

## 8. 理论贡献
1. 理论视角创新...
2. 机制系统化梳理...

## 9. 应用价值
为地方政府、乡村文化工作者...

## 10. 理论依据
论文的分析建立在多个理论传统之上...

## 11. 详细分析
本论文的核心机制是一个关于...
```

---

## 测试结果

**测试论文**: 类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径
**测试时间**: 2026-02-03 17:06
**测试状态**: ✅ 全部通过

| 层级 | 输出文件 | 文件大小 | 格式验证 |
|------|---------|---------|---------|
| L1_Context | L1_Context.md | 11 KB | ✅ 完全符合 |
| L2_Theory | L2_Theory.md | 19 KB | ✅ 完全符合 |
| L3_Logic | L3_Logic.md | 12 KB | ✅ 完全符合 (Theoretical 格式) |
| L4_Value | L4_Value.md | 9 KB | ✅ 完全符合 |
| Full Report | ..._Full_Report.md | 52 KB | ✅ 完全符合 |

### 体裁检测

- **检测方法**: 从 L1_Context 输出中自动提取
- **检测精度**: ✅ 准确识别为 "Theoretical"
- **L3 自适应**: ✅ 根据体裁自动调整输出格式

---

## 优势对比

| 维度 | v1 (JSON) | v2 (Markdown) | 改进 |
|------|-----------|---------------|------|
| **稳定性** | 可能 JSON 格式错误 | 直接输出，格式稳定 | ✅ 无需 json_repair |
| **解析复杂度** | 需要解析+错误处理 | 无需解析，直接可用 | ✅ 简化 50% |
| **可读性** | 需要转换查看 | 直接可读 | ✅ 用户体验提升 |
| **元数据提取** | JSON 键值对 | 正则表达式 `## 数字.` | ✅ 统一格式 |
| **人工审阅** | 需要 JSON 工具 | 任何文本编辑器 | ✅ 便捷性提升 |
| **版本控制** | Git diff 不友好 | Markdown diff 友好 | ✅ 可追溯性 |

---

## 下一步集成

### 阶段 1: 替换批量流水线 (当前优先级)

**文件**: `run_batch_pipeline.py`

**修改位置**: 第 122-132 行 (QUAL 路由)

```python
# 旧代码 (第 122-132 行)
if paper_type == "QUAL":
    from social_science_analyzer import SocialScienceAnalyzer
    analyzer = SocialScienceAnalyzer()
    analyzer.run_full_analysis(seg_md_path, paper_output_dir)

# 新代码
if paper_type == "QUAL":
    from social_science_analyzer_v2 import SocialScienceAnalyzerV2
    analyzer = SocialScienceAnalyzerV2()
    analyzer.run_full_analysis(seg_md_path, paper_output_dir)
```

### 阶段 2: 开发元数据提取工具 (后续)

**新文件**: `qual_metadata_extractor.py`

**功能**: 从 Markdown 中提取结构化元数据

```python
def extract_l1_metadata(md_path):
    """提取 L1 层元数据"""
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    return {
        "genre": extract_section(content, 1),
        "core_issue": extract_section(content, 2),
        "policies": extract_section(content, 3),
        "status_data": extract_section(content, 4),
        "theoretical_importance": extract_section(content, 5),
        "practical_importance": extract_section(content, 6)
    }
```

---

## 故障排查

### 常见问题

| 问题 | 原因 | 解决方案 |
|------|------|---------|
| 提示词文件未找到 | 路径错误 | 确保 `prompts/qual_analysis/` 目录存在 |
| LLM 不遵循 Markdown 格式 | 系统提示词不够强调 | 已在系统提示词中强调 `IMPORTANT` |
| 体裁提取失败 | L1 格式不符合预期 | 使用默认值 "Theoretical" |
| 编码错误 | Windows 控制台 | 不影响文件输出，可忽略 |

---

## 版本历史

### v2.0 (2026-02-03) - Markdown 格式输出

**新增功能**:
- ✅ 直接 Markdown 输出 (无需 JSON 解析)
- ✅ 动态加载外部提示词文件
- ✅ L3 层体裁自适应
- ✅ 自动体裁提取
- ✅ 简化的保存方法
- ✅ 总报告自动生成

**测试状态**: ✅ 通过

### v1.0 (2026-02-02) - JSON 格式输出

**功能**:
- JSON 格式输出
- 静态提示词
- 手工生成 Markdown

**状态**: ⚠️ 已备份为 `social_science_analyzer_v1_backup.py`

---

**维护者**: Deep Reading Agent Team
**联系**: 通过 GitHub Issues 报告问题
