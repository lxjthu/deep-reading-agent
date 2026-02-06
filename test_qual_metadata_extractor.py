"""
测试 QUAL 元数据提取器
"""

import os
from dotenv import load_dotenv
from qual_metadata_extractor.extractor import extract_qual_metadata

load_dotenv()

# 测试配置
PAPER_DIR = "social_science_results_v2/类ChatGPT人工智能技术赋能乡村文化振兴：机遇、挑战和路径"
PDF_DIR = "E:/pdf/001"

def test_env_vars():
    """测试环境变量"""
    print("=== 测试环境变量 ===")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    qwen_key = os.getenv("QWEN_API_KEY")
    
    print(f"DEEPSEEK_API_KEY: {'[OK] 已设置' if deepseek_key else '[X] 未设置'}")
    print(f"QWEN_API_KEY: {'[OK] 已设置' if qwen_key else '[X] 未设置'}")
    
    if not deepseek_key or not qwen_key:
        print("\n[!] 警告: 缺少必要的环境变量")
        return False
    print("[OK] 所有环境变量已设置\n")
    return True

def test_file_paths():
    """测试文件路径"""
    print("=== 测试文件路径 ===")
    
    # 检查论文目录
    if not os.path.exists(PAPER_DIR):
        print(f"[X] 论文目录不存在: {PAPER_DIR}")
        return False
    print(f"[OK] 论文目录存在: {PAPER_DIR}")
    
    # 检查层级文件
    layers = ["L1_Context.md", "L2_Theory.md", "L3_Logic.md", "L4_Value.md"]
    for layer in layers:
        layer_path = os.path.join(PAPER_DIR, layer)
        if os.path.exists(layer_path):
            print(f"[OK] {layer} 存在")
        else:
            print(f"[X] {layer} 不存在")
            return False
    
    # 检查 PDF 目录
    if not os.path.exists(PDF_DIR):
        print(f"[X] PDF 目录不存在: {PDF_DIR}")
        return False
    print(f"[OK] PDF 目录存在: {PDF_DIR}\n")
    
    return True

def test_extraction():
    """测试提取流程"""
    print("=== 测试提取流程 ===")
    
    try:
        extract_qual_metadata(PAPER_DIR, PDF_DIR)
        print("[OK] 提取完成\n")
        return True
    except Exception as e:
        print(f"[X] 提取失败: {e}\n")
        return False

def verify_output():
    """验证输出结果"""
    print("=== 验证输出结果 ===")
    
    # 检查 L1_Context.md
    l1_path = os.path.join(PAPER_DIR, "L1_Context.md")
    with open(l1_path, 'r', encoding='utf-8') as f:
        l1_content = f.read()
    
    # 检查 frontmatter
    if l1_content.startswith("---"):
        print("[OK] YAML Frontmatter 已注入")
        
        # 检查基础字段
        base_checks = [
            ("title", "论文标题"),
            ("authors", "作者列表"),
            ("journal", "期刊名称"),
            ("year", "发表年份"),
        ]
        
        for field, desc in base_checks:
            if field in l1_content:
                print(f"  [OK] {desc} 存在")
            else:
                print(f"  [X] {desc} 缺失")
        
        # 检查 L1 的小标题元数据（扁平结构）
        l1_checks = [
            "1. 论文分类",
            "2. 核心问题",
            "3. 政策文件",
            "4. 现状数据",
        ]
        
        l1_subsections_found = 0
        for section in l1_checks:
            if section in l1_content:
                l1_subsections_found += 1
        
        if l1_subsections_found >= 3:
            print(f"  [OK] L1 小标题元数据存在（找到 {l1_subsections_found} 个）")
        else:
            print(f"  [X] L1 小标题元数据缺失（只找到 {l1_subsections_found} 个）")
        
        # 检查不应该有其他层的元数据
        if "L1_Context_subsections:" in l1_content:
            print("  [X] 仍有嵌套的 L1_Context_subsections（应该扁平化）")
        else:
            print("  [OK] 元数据已扁平化（无嵌套结构）")
    else:
        print("[X] YAML Frontmatter 未注入")
        return False
    
    # 检查导航链接
    if "## 导航" in l1_content:
        print("[OK] 导航链接已添加")
        
        if "返回总报告" in l1_content:
            print("  [OK] 返回总报告链接存在")
        
        if "[[L2_Theory]]" in l1_content and "[[L3_Logic]]" in l1_content and "[[L4_Value]]" in l1_content:
            print("  [OK] 其他层级链接存在")
    else:
        print("[X] 导航链接未添加")
        return False
    
    # 检查 L2_Theory.md（只应该有自己的小标题）
    l2_path = os.path.join(PAPER_DIR, "L2_Theory.md")
    with open(l2_path, 'r', encoding='utf-8') as f:
        l2_content = f.read()
    
    # L2 应该有自己的小标题
    if "1. 经典理论回顾" in l2_content or "2. 核心构念" in l2_content:
        print("[OK] L2_Theory 包含自己的小标题元数据")
    else:
        print("[X] L2_Theory 缺少自己的小标题元数据")
    
    # 检查 Full_Report（只有基础元数据，无小标题，无导航）
    full_report_path = os.path.join(PAPER_DIR, f"{os.path.basename(PAPER_DIR)}_Full_Report.md")
    if os.path.exists(full_report_path):
        with open(full_report_path, 'r', encoding='utf-8') as f:
            fr_content = f.read()
        
        if fr_content.startswith("---"):
            # 提取 frontmatter 部分
            fm_end = fr_content.find("\n---\n", 4)
            if fm_end != -1:
                frontmatter = fr_content[:fm_end]
            else:
                frontmatter = fr_content
            
            # 应该有基础元数据
            if "title:" in frontmatter and "authors:" in frontmatter:
                print("[OK] Full_Report 包含基础元数据")
            else:
                print("[X] Full_Report 缺少基础元数据")
            
            # 不应该有小标题元数据（只在 frontmatter 中检查）
            if "1. 论文分类:" not in frontmatter and "1. 经典理论回顾:" not in frontmatter:
                print("[OK] Full_Report 不包含小标题元数据")
            else:
                print("[X] Full_Report 包含了小标题元数据（不应该有）")
            
            # 不应该有导航
            if "## 导航" not in fr_content:
                print("[OK] Full_Report 不包含导航链接")
            else:
                print("[X] Full_Report 包含导航链接（不应该有）")
    
    print()
    return True

if __name__ == "__main__":
    print("开始测试 QUAL 元数据提取器\n")
    
    # 运行所有测试
    tests = [
        test_env_vars,
        test_file_paths,
        test_extraction,
        verify_output,
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"[X] 测试异常: {e}\n")
            results.append(False)
    
    # 总结
    print("=" * 50)
    if all(results):
        print("[OK] 所有测试通过！")
    else:
        print("[X] 部分测试失败")
        failed_count = sum(1 for r in results if not r)
        print(f"  失败测试数: {failed_count}/{len(results)}")
