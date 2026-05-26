# Deep Reading Agent 运维报告模板

## 📊 系统状态摘要

| 组件 | 状态 | 详情 |
|------|------|------|
| 后端 API | ✅ 正常 | PID: {backend_pid}, 运行时长: {backend_uptime} |
| 前端服务 | ✅ 正常 | PID: {frontend_pid} |
| Cloudflare Tunnel | ✅ 正常 | PID: {tunnel_pid} |
| 公网访问 | ✅ 200 | https://deepreading.qzz.io/ |

---

## 📈 资源使用

| 指标 | 当前值 | 阈值 | 状态 |
|------|--------|------|------|
| 磁盘使用率 | {disk_usage}% | 80% | {disk_status} |
| 内存使用率 | {mem_usage}% | 85% | {mem_status} |
| 数据库大小 | {db_size} | - | ✅ |
| 上传文件 | {upload_size} | - | ✅ |
| 精读结果 | {results_size} | - | ✅ |

---

## 👥 用户与任务

- **注册用户**: {user_count} 人 (admin: {admin_count}, normal: {normal_count}, vip: {vip_count})
- **总任务数**: {job_count}
- **任务状态分布**: {job_statuses}
- **最近活跃**: {recent_activity}

---

## 💬 用户反馈

- **待处理反馈**: {open_feedback} 条
- **总反馈数**: {total_feedback} 条
- **反馈类型分布**: {feedback_types}

---

## ⚠️ 异常与报错

### 后端日志 (最近200行)
- **ERROR 计数**: {backend_errors}
- **关键异常**: {backend_exceptions}

### Tunnel 日志 (最近50行)
- **ERROR 计数**: {tunnel_errors}
- **主要问题**: {tunnel_issues}

### 清理任务
- **最近清理**: {cleanup_last_run}
- **清理结果**: {cleanup_result}

---

## 🔧 待修复问题

1. **{issue_1_title}**
   - 严重程度: {issue_1_severity}
   - 描述: {issue_1_desc}
   - 影响: {issue_1_impact}

2. **{issue_2_title}**
   - 严重程度: {issue_2_severity}
   - 描述: {issue_2_desc}
   - 影响: {issue_2_impact}

---

## 🛠️ 修复方案

### 方案 A: {fix_1_title}
- **步骤**: {fix_1_steps}
- **预计时间**: {fix_1_time}
- **风险**: {fix_1_risk}
- **回滚方案**: {fix_1_rollback}

### 方案 B: {fix_2_title}
- **步骤**: {fix_2_steps}
- **预计时间**: {fix_2_time}
- **风险**: {fix_2_risk}

---

## 📋 建议操作

- [ ] {action_1}
- [ ] {action_2}
- [ ] {action_3}

---

*报告生成时间: {report_time}*
*下次检查: {next_check}*
