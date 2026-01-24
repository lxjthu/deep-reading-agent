# 学术文献智能分析与代码精修工具使用指南

本工具专为计量经济学与社会科学研究者设计，结合 **Moonshot AI (Kimi)** 的长文本理解能力与 **DeepSeek (R1)** 的深度推理能力，实现从 PDF 文献到结构化数据、再到专家级 Stata 代码的全流程自动化。

---

## 🚀 核心功能

1.  **多语言智能提取**：支持中文/英文 PDF 文献，统一输出中文研读报告。
2.  **增量式处理**：自动识别新放入的文献，避免重复分析，节省 Token。
3.  **专家级代码生成**：
    *   **Acemoglu 模式**：模拟 MIT 教授视角，基于 DeepSeek-R1 思考模式。
    *   **深度实证策略**：自动补充稳健性检验（平行趋势、安慰剂检验等）。
    *   **中文注释**：生成详细的中文代码注释与实证避坑指南。
4.  **结构化输出**：自动生成 Excel 汇总表与 Markdown 详细报告。
5.  **社科深度阅读**：专为管理学/社会学定性研究设计，采用“四层金字塔”模型（背景-理论-逻辑-价值）进行深度提取。

---

## 🛠️ 环境配置

### 1. API Key 设置
在项目根目录创建或修改 `.env` 文件，填入您的密钥：

```ini
# Kimi (Moonshot AI) - 用于文献阅读与信息提取
OPENAI_API_KEY=sk-your-kimi-key
OPENAI_BASE_URL=https://api.moonshot.cn/v1
OPENAI_MODEL=moonshot-v1-auto  # 自动适配长短文本

# DeepSeek - 用于 Stata 代码深度精修 (R1 思考模式)
DEEPSEEK_API_KEY=sk-your-deepseek-key
```

### 2. 依赖安装
确保已安装 Python 环境，并运行：
```bash
pip install -r requirements.txt
```

---

## 📖 使用流程

### 第一步：文献分析 (Analysis)
将 PDF 文件放入 `pdf/` 文件夹中，然后运行：

```powershell
.\run_analyzer.ps1 -InputPath "pdf"
```

*   **功能**：读取 PDF -> Kimi 提取信息 -> 生成初版 Markdown 报告 -> 更新 `results.xlsx`。
*   **特性**：默认开启**增量模式**，只处理新文件。
*   **强制重跑**：如果需要重新分析所有文件，请加参数：
    ```powershell
    .\run_analyzer.ps1 -InputPath "pdf" --force
    ```

### 第二步：代码精修 (Refinement)
分析完成后，运行精修脚本，启用 DeepSeek 专家模式对代码进行升级：

```powershell
.\venv\Scripts\python refine_stata.py
```

*   **功能**：扫描 `reports/` 下的报告 -> DeepSeek 深度思考 -> 重写 Stata 代码段。
*   **特性**：
    *   自动添加 `(Expert Refined)` 标记。
    *   支持**断点续传**，自动跳过已精修的报告。

### 第三步：社科文献深度阅读 (Social Science Scholar)
针对管理学、社会学等定性/案例/组态研究文献，启用全新的“四层金字塔”深度分析模式：

```powershell
python run_social_science_task.py
```

*   **功能**：自动完成 PDF 切分 -> L1-L4 分层分析 -> 全景报告生成 -> 双向链接注入。
*   **模型**：
    *   **L1 Context**：政策背景与现状数据。
    *   **L2 Theory**：构念界定与理论框架。
    *   **L3 Logic**：案例过程与组态路径。
    *   **L4 Value**：研究缺口与实践启示。
*   **产出**：`social_science_results_v2/` 下的结构化 Markdown (含 Obsidian 元数据) 和 Excel 汇总表。

---

## 📂 输出文件说明

### 1. 汇总表格 (`results.xlsx`)
包含所有文献的结构化信息，支持以下字段：
*   **基础信息**：标题、作者、期刊、年份。
*   **核心摘要**：研究背景、理论意义、实践意义。
*   **变量定义**：被解释变量、解释变量、机制变量、工具变量、控制变量（均为中文定义）。
*   **方法论**：研究思路、模型设定、数据来源。
*   **参考文献**：自动截取前 5 篇核心文献。

### 2. 研读报告 (`reports/*.md`)
每篇论文对应的详细阅读笔记，包含：
*   **完整参考文献列表**。
*   **研究逻辑链**。
*   **专家级 Stata 代码**：
    *   包含 `reghdfe` 等高阶命令。
    *   包含平行趋势检验、IV 检验等稳健性检查。
    *   包含“实证研究注意事项”章节。

---

## ❓ 常见问题

**Q: 英文论文能处理吗？**
A: **完美支持**。系统会自动识别英文内容，并强制用**中文**输出所有摘要和定义，仅保留作者名和专有名词为英文。

**Q: 为什么代码精修比较慢？**
A: DeepSeek-R1 (reasoner) 模式需要进行“思维链”推理，通常比普通对话模型慢，但生成的代码质量和逻辑严密性有质的飞跃。

**Q: `results.xlsx` 无法写入怎么办？**
A: 请确保文件未在 Excel 中打开。如果无法关闭，程序会自动创建一个新文件（如 `results_new_7.xlsx`）以防数据丢失。
