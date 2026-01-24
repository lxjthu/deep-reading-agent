import pandas as pd
import os

excel_path = r"d:\code\skill\pdf_raw_md_analysis.xlsx"
filename = "2-人口与发展-Bittersweet--Grandparenting-and-elderly-mental-heal_2026_Journal-of-Developm_raw.md"

new_data = {
    "Filename": filename,
    "Title": "Bittersweet: Grandparenting and elderly mental health in the two-child policy era",
    "Authors": "Dapeng Chen, Shin-Yi Chou, Bingjin Xue",
    "Journal": "Journal of Development Economics",
    "Year": "2026",
    
    "Research Theme": "中国全面二孩政策对隔代照料负担及老年人心理健康的影响。",
    "Problem": "生育政策放开导致的照料负担加重，是否会损害祖辈的心理健康？",
    "Contribution": "利用DID模型提供因果证据；揭示了鼓励生育政策对老年福利的非预期负面影响；发现父系文化规范下的异质性效应。",
    
    "Theory Base": "代际转移理论、角色压力理论 (Role Strain) 与角色增益理论 (Role Enhancement) 的权衡。",
    "Hypothesis": "二孩政策增加了孙子女数量和照料强度，进而导致祖辈心理健康水平下降（支持角色压力假说）。",
    
    "Data Source": "中国健康与养老追踪调查 (CHARLS) 面板数据 (2011, 2013, 2015, 2018)。",
    "Sample Info": "45岁及以上中老年人，样本量40,628个观测值；处理组为2016年时长子/长女处于20-35岁生育旺盛期的祖辈。",
    
    "Dep. Var (Y)": "心理健康 (CESD-10量表得分，0-30分)，以及抑郁症状指标。",
    "Indep. Var (X)": "政策冲击 (Post × Treated)，其中Treated界定为子女处于生育适龄期。",
    "Controls": "年龄、性别、婚姻、户口、就业退休状态、家庭结构、基线健康状况、社区固定效应等。",
    
    "Model": "双重差分模型 (Difference-in-Differences, DID) 及事件研究法 (Event Study)。",
    "Strategy": "利用2016年政策外生冲击 + 子女出生年份决定的暴露程度。",
    "IV/Mechanism": "机制验证：孙子女数量、隔代照料概率、照料时长、居住安排（同住/近住）。",
    
    "Findings": "政策导致处理组孙子女数增加0.22个，照料概率增加14.5%；CESD-10得分显著增加0.51分（心理变差），主要表现为睡眠不安、易怒。效应在城市和父系祖母中更强。",
    "Weakness": "虽然排除了收入机制，但难以完全排除除照料外的其他心理影响渠道；自我报告的心理指标可能存在测量误差。",
    
    "Stata Code": """reghdfe cesd10_score c.post#c.treated i.treated#c.wave_trend $controls, ///
    absorb(ind_id community_id#wave) vce(cluster first_child_birth_cohort)"""
}

if os.path.exists(excel_path):
    try:
        df = pd.read_excel(excel_path)
    except Exception as e:
        print(f"Error reading excel: {e}")
        df = pd.DataFrame()

    if not df.empty:
        # Check if exists and update
        if "Filename" in df.columns and filename in df["Filename"].values:
            print(f"Updating existing record for {filename}")
            idx = df.index[df["Filename"] == filename].tolist()[0]
            for key, value in new_data.items():
                if key in df.columns:
                    df.at[idx, key] = value
        else:
            print(f"Appending new record for {filename}")
            new_row = pd.DataFrame([new_data])
            df = pd.concat([df, new_row], ignore_index=True)
            
        try:
            df.to_excel(excel_path, index=False)
            print(f"Success. Saved to {excel_path}")
        except PermissionError:
            new_path = excel_path.replace(".xlsx", "_fixed.xlsx")
            df.to_excel(new_path, index=False)
            print(f"File locked. Saved to new file: {new_path}")
    else:
        print("DataFrame is empty.")
else:
    print("Excel file not found.")
