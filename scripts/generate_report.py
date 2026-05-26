#!/usr/bin/env python3
"""
Deep Reading Agent - 每日运维报告生成器
读取 JSON 检查报告，生成结构化运维报告
"""

import json
import sys
from datetime import datetime
from pathlib import Path

REPORT_DIR = Path("/root/.openclaw/workspace/deep-reading-agent/reports")
TEMPLATE_PATH = Path("/root/.openclaw/workspace/deep-reading-agent/scripts/report_template.md")

def load_report(date_str: str = None) -> dict:
    if date_str is None:
        date_str = datetime.now().strftime("%Y%m%d")
    report_file = REPORT_DIR / f"daily_{date_str}.json"
    if not report_file.exists():
        print(f"报告文件不存在: {report_file}")
        sys.exit(1)
    with open(report_file, "r", encoding="utf-8") as f:
        return json.load(f)

def analyze_issues(data: dict) -> list:
    """分析检查数据，提取待修复问题"""
    issues = []
    
    # 1. 服务状态检查
    checks = data.get("checks", {})
    if checks.get("backend", {}).get("status_code") != 200:
        issues.append({
            "title": "后端服务异常",
            "severity": "P0",
            "desc": f"后端返回 HTTP {checks['backend']['status_code']}",
            "impact": "所有API功能不可用，用户无法提交任务"
        })
    if checks.get("tunnel", {}).get("status_code") != 200:
        issues.append({
            "title": "公网隧道异常",
            "severity": "P0", 
            "desc": f"Cloudflare Tunnel 返回 HTTP {checks['tunnel']['status_code']}",
            "impact": "外部用户无法访问系统"
        })
    
    # 2. 资源检查
    resources = data.get("resources", {})
    disk_pct = resources.get("disk_usage_percent", 0)
    if isinstance(disk_pct, str):
        disk_pct = int(disk_pct) if disk_pct.isdigit() else 0
    if disk_pct > 80:
        issues.append({
            "title": "磁盘空间不足",
            "severity": "P1",
            "desc": f"磁盘使用率 {disk_pct}%，超过80%阈值",
            "impact": "可能导致上传失败、数据库写入错误"
        })
    
    mem_pct = resources.get("memory_usage_percent", 0)
    if isinstance(mem_pct, str):
        mem_pct = float(mem_pct)
    if mem_pct > 85:
        issues.append({
            "title": "内存使用率过高",
            "severity": "P1",
            "desc": f"内存使用率 {mem_pct}%",
            "impact": "可能导致OOM，服务响应变慢"
        })
    
    # 3. 错误日志检查
    errors = data.get("errors", {})
    backend_err = errors.get("backend_error_count_200lines", 0)
    if isinstance(backend_err, str):
        backend_err = int(backend_err) if backend_err.isdigit() else 0
    if backend_err > 0:
        issues.append({
            "title": f"后端出现 {backend_err} 条错误日志",
            "severity": "P2",
            "desc": "最近200行日志中发现 ERROR/Exception",
            "impact": "可能存在未处理的异常，需要排查"
        })
    
    tunnel_err = errors.get("tunnel_error_count_50lines", 0)
    if isinstance(tunnel_err, str):
        tunnel_err = int(tunnel_err) if tunnel_err.isdigit() else 0
    if tunnel_err > 5:
        issues.append({
            "title": f"Tunnel 出现 {tunnel_err} 条错误",
            "severity": "P2",
            "desc": "Cloudflare Tunnel 连接不稳定",
            "impact": "用户访问可能间歇性中断"
        })
    
    # 4. 数据库检查
    db = data.get("database", {})
    job_statuses = db.get("job_statuses", {})
    failed_jobs = job_statuses.get("failed", 0)
    if isinstance(failed_jobs, str):
        failed_jobs = int(failed_jobs)
    if failed_jobs > 0:
        issues.append({
            "title": f"存在 {failed_jobs} 个失败任务",
            "severity": "P2",
            "desc": "任务执行失败，可能需要用户重新提交",
            "impact": "用户体验受损，可能丢失处理结果"
        })
    
    # 5. 反馈检查
    open_feedback = db.get("feedback_open", 0)
    if isinstance(open_feedback, str):
        open_feedback = int(open_feedback)
    if open_feedback > 0:
        issues.append({
            "title": f"有 {open_feedback} 条未处理用户反馈",
            "severity": "P2",
            "desc": "用户提交的反馈/bug报告待处理",
            "impact": "用户问题未解决，满意度下降"
        })
    
    # 6. 长时间运行的服务（可能需要重启）
    backend_uptime = checks.get("backend", {}).get("uptime", "")
    if backend_uptime and isinstance(backend_uptime, str):
        # 简单检查：如果运行超过7天
        if "-" in backend_uptime or (":" in backend_uptime and backend_uptime.count(":") >= 2):
            # 格式可能是 "7-12:34:56" 或 "12:34:56"
            issues.append({
                "title": "后端服务运行时间较长",
                "severity": "P3",
                "desc": f"后端已运行 {backend_uptime}，建议计划内重启",
                "impact": "内存泄漏累积，建议低峰期重启"
            })
    
    return issues

def generate_fix_proposals(issues: list) -> list:
    """为每个问题生成修复方案"""
    proposals = []
    for issue in issues:
        if issue["title"] == "后端服务异常":
            proposals.append({
                "title": "重启后端服务",
                "steps": [
                    "1. 检查后端日志定位崩溃原因",
                    "2. 执行: pkill -f 'uvicorn main:app'",
                    "3. 等待2秒后重新启动",
                    "4. 验证 /health 端点返回200"
                ],
                "time": "2-5分钟",
                "risk": "正在处理的任务会中断",
                "rollback": "检查之前的日志，回滚到上一个稳定版本"
            })
        elif issue["title"] == "公网隧道异常":
            proposals.append({
                "title": "重启 Cloudflare Tunnel",
                "steps": [
                    "1. pkill -f 'cloudflared tunnel'",
                    "2. 检查 /root/.cloudflared/config.yml 配置",
                    "3. 重新启动 tunnel",
                    "4. 验证 deepreading.qzz.io 可访问"
                ],
                "time": "3-5分钟",
                "risk": "公网访问中断2-3分钟",
                "rollback": "检查 Cloudflare 控制台隧道状态"
            })
        elif issue["title"].startswith("磁盘空间"):
            proposals.append({
                "title": "清理磁盘空间",
                "steps": [
                    "1. 清理 /tmp 目录旧文件",
                    "2. 清理 deep_reading_results 中旧结果",
                    "3. 检查 _uploads 中孤立文件",
                    "4. 必要时扩展磁盘"
                ],
                "time": "10-20分钟",
                "risk": "可能误删用户数据，需先备份",
                "rollback": "从备份恢复误删文件"
            })
        elif issue["title"].startswith("后端出现"):
            proposals.append({
                "title": "排查后端错误",
                "steps": [
                    "1. 查看 /tmp/fastapi.log 错误详情",
                    "2. 定位错误发生的模块",
                    "3. 根据错误类型修复代码或配置",
                    "4. 部署修复并验证"
                ],
                "time": "15-60分钟",
                "risk": "修复可能引入新问题",
                "rollback": "git revert 到上一个稳定提交"
            })
        elif issue["title"].startswith("存在") and "失败任务" in issue["title"]:
            proposals.append({
                "title": "处理失败任务",
                "steps": [
                    "1. 查询失败任务的 error_msg",
                    "2. 分类：可重试 / 需修复 / 用户错误",
                    "3. 对可重试任务重新提交",
                    "4. 对系统性错误修复后通知用户"
                ],
                "time": "10-30分钟",
                "risk": "重试可能再次失败",
                "rollback": "标记任务为 manual_review"
            })
        elif issue["title"].startswith("有") and "未处理用户反馈" in issue["title"]:
            proposals.append({
                "title": "处理用户反馈",
                "steps": [
                    "1. 登录管理后台查看反馈列表",
                    "2. 按优先级排序",
                    "3. 对bug类反馈进行复现和修复",
                    "4. 给用户回复处理结果"
                ],
                "time": "30-120分钟",
                "risk": "修复可能引入回归问题",
                "rollback": "回滚修复代码"
            })
    
    return proposals

def generate_report(data: dict, issues: list, proposals: list) -> str:
    """生成最终报告"""
    checks = data.get("checks", {})
    resources = data.get("resources", {})
    db = data.get("database", {})
    errors = data.get("errors", {})
    
    # 状态判断
    def status_emoji(val, threshold, direction="lt"):
        if direction == "lt":
            return "✅" if val < threshold else "⚠️"
        return "✅" if val > threshold else "⚠️"
    
    disk_pct = resources.get("disk_usage_percent", 0)
    if isinstance(disk_pct, str):
        disk_pct = int(disk_pct) if disk_pct.isdigit() else 0
    mem_pct = resources.get("memory_usage_percent", 0)
    if isinstance(mem_pct, str):
        mem_pct = float(mem_pct)
    
    # 构建报告
    lines = []
    lines.append("# 🔍 Deep Reading Agent 每日运维报告")
    lines.append(f"**生成时间**: {data.get('timestamp', 'unknown')}")
    lines.append("")
    
    # 系统状态
    lines.append("## 📊 系统状态摘要")
    lines.append("")
    lines.append("| 组件 | 状态 | 详情 |")
    lines.append("|------|------|------|")
    backend_pid = checks.get("backend", {}).get("pid", "N/A")
    backend_uptime = checks.get("backend", {}).get("uptime", "unknown")
    lines.append(f"| 后端 API | {'✅ 正常' if checks.get('backend',{}).get('status_code')==200 else '❌ 异常'} | PID: {backend_pid}, 运行: {backend_uptime} |")
    lines.append(f"| 前端服务 | {'✅ 正常' if checks.get('frontend',{}).get('status_code')==200 else '❌ 异常'} | PID: {checks.get('frontend',{}).get('pid','N/A')} |")
    lines.append(f"| 公网隧道 | {'✅ 正常' if checks.get('tunnel',{}).get('status_code')==200 else '❌ 异常'} | PID: {checks.get('tunnel',{}).get('pid','N/A')} |")
    lines.append(f"| 公网访问 | {'✅ 200' if checks.get('tunnel',{}).get('status_code')==200 else '❌ 异常'} | https://deepreading.qzz.io/ |")
    lines.append("")
    
    # 资源使用
    lines.append("## 📈 资源使用")
    lines.append("")
    lines.append("| 指标 | 当前值 | 状态 |")
    lines.append("|------|--------|------|")
    lines.append(f"| 磁盘使用率 | {disk_pct}% | {'✅' if disk_pct < 80 else '⚠️ 需关注'} |")
    lines.append(f"| 内存使用率 | {mem_pct}% | {'✅' if mem_pct < 85 else '⚠️ 需关注'} |")
    lines.append(f"| 数据库大小 | {resources.get('db_size', 'unknown')} | ✅ |")
    lines.append(f"| 上传文件 | {resources.get('uploads_size', 'unknown')} | ✅ |")
    lines.append(f"| 精读结果 | {resources.get('results_size', 'unknown')} | ✅ |")
    lines.append("")
    
    # 用户与任务
    lines.append("## 👥 用户与任务")
    lines.append("")
    lines.append(f"- **注册用户**: {db.get('users', 'N/A')} 人")
    lines.append(f"- **总任务数**: {db.get('jobs', 'N/A')}")
    job_statuses = db.get("job_statuses", {})
    if job_statuses:
        status_str = ", ".join([f"{k}: {v}" for k, v in job_statuses.items()])
        lines.append(f"- **任务状态**: {status_str}")
    recent_jobs = db.get("recent_jobs", [])
    if recent_jobs:
        lines.append(f"- **最近任务**: {len(recent_jobs)} 条")
        for job in recent_jobs[:3]:
            lines.append(f"  - #{job.get('id', '?')[:8]} {job.get('type', '?')} ({job.get('status', '?')})")
    lines.append(f"- **AI 会话**: {db.get('agent_sessions', 0)} 个会话, {db.get('agent_messages', 0)} 条消息")
    lines.append("")
    
    # 异常与报错
    lines.append("## ⚠️ 异常与报错")
    lines.append("")
    backend_err = errors.get("backend_error_count_200lines", 0)
    tunnel_err = errors.get("tunnel_error_count_50lines", 0)
    lines.append(f"- **后端错误** (最近200行): {backend_err} 条")
    lines.append(f"- **Tunnel 错误** (最近50行): {tunnel_err} 条")
    cleanup = data.get("cleanup_log", "")
    if cleanup:
        lines.append(f"- **最近清理**: {cleanup.split(chr(10))[-1][:100]}")
    lines.append("")
    
    # 待修复问题
    if issues:
        lines.append("## 🔧 待修复问题")
        lines.append("")
        for i, issue in enumerate(issues, 1):
            severity_emoji = {"P0": "🔴", "P1": "🟠", "P2": "🟡", "P3": "🔵"}.get(issue["severity"], "⚪")
            lines.append(f"### {i}. {severity_emoji} {issue['title']} ({issue['severity']})")
            lines.append(f"- **描述**: {issue['desc']}")
            lines.append(f"- **影响**: {issue['impact']}")
            lines.append("")
    else:
        lines.append("## ✅ 系统健康")
        lines.append("")
        lines.append("未发现待修复问题，系统运行正常。")
        lines.append("")
    
    # 修复方案
    if proposals:
        lines.append("## 🛠️ 修复方案")
        lines.append("")
        for i, prop in enumerate(proposals, 1):
            lines.append(f"### 方案 {i}: {prop['title']}")
            lines.append(f"- **预计时间**: {prop['time']}")
            lines.append(f"- **风险**: {prop['risk']}")
            if prop.get('rollback'):
                lines.append(f"- **回滚方案**: {prop['rollback']}")
            lines.append("- **步骤**:")
            for step in prop.get("steps", []):
                lines.append(f"  {step}")
            lines.append("")
    
    # 建议操作
    lines.append("## 📋 今日建议")
    lines.append("")
    if not issues:
        lines.append("- [ ] 系统健康，无需紧急操作")
        lines.append("- [ ] 可考虑在低峰期进行例行维护")
    else:
        p0_issues = [i for i in issues if i["severity"] == "P0"]
        if p0_issues:
            lines.append("- [ ] **优先处理 P0 问题** (服务不可用)")
        p1_issues = [i for i in issues if i["severity"] == "P1"]
        if p1_issues:
            lines.append("- [ ] 处理 P1 问题 (资源/性能)")
        lines.append("- [ ] 确认修复后重新运行健康检查")
        lines.append("- [ ] 观察15分钟确认系统稳定")
    lines.append("")
    
    lines.append("---")
    lines.append(f"*下次检查: 明日 {datetime.now().strftime('%H:%M')}*")
    
    return "\n".join(lines)

def main():
    date_str = sys.argv[1] if len(sys.argv) > 1 else None
    data = load_report(date_str)
    issues = analyze_issues(data)
    proposals = generate_fix_proposals(issues)
    report = generate_report(data, issues, proposals)
    
    # 输出报告
    print(report)
    
    # 保存报告
    date_str = date_str or datetime.now().strftime("%Y%m%d")
    report_file = REPORT_DIR / f"report_{date_str}.md"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"\n报告已保存: {report_file}", file=sys.stderr)

if __name__ == "__main__":
    main()
