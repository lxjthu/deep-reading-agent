# 服务器报错排查记录

> 适用项目：`deep-reading-agent`  
> 记录日期：2026-05-03  
> 服务器环境：Ubuntu, Nginx, Cloudflare Tunnel, FastAPI (uvicorn)

---

## 问题 1：文献筛选时报错 `MultipleResultsFound`

### 错误现象

前端上传文献后，点击筛选/分析时返回：

```
❌ Unexpected token 'I', "Internal S"... is not valid JSON
```

实际是服务器返回了 `500 Internal Server Error`，前端无法解析为 JSON。

### 排查过程

查看服务器日志：

```bash
tail -100 /tmp/fastapi.log
```

发现关键错误：

```
sqlalchemy.exc.MultipleResultsFound: Multiple rows were found when one or none was required
```

错误堆栈指向：

```
File "backend/routers/filter.py", line 490, in start_filter
    prompt_template = await get_effective_prompt_text(...)
File "backend/prompt_service.py", line 84, in _get_template_row
    ).scalar_one_or_none()
```

### 根因分析

`prompt_templates` 表中存在重复记录，`_get_template_row` 函数使用 `scalar_one_or_none()` 期望返回 1 行，但实际返回了多行。

**为什么本地正常**：本地数据库可能没有重复记录，或者使用了不同的用户/配置。

### 解决方案

在服务器上执行以下步骤：

#### 1. 创建修复脚本

```bash
cat > /tmp/fix_prompt.py << 'EOF'
import sqlite3

conn = sqlite3.connect('/root/.openclaw/workspace/deep-reading-agent/db/app.sqlite')
cursor = conn.cursor()

# 查看重复记录
cursor.execute("""
    SELECT prompt_type, prompt_key, scope, owner_user_id, COUNT(*) as cnt
    FROM prompt_templates
    GROUP BY prompt_type, prompt_key, scope, owner_user_id
    HAVING cnt > 1
""")
rows = cursor.fetchall()
print(f"发现 {len(rows)} 组重复记录")
for row in rows:
    print(f"  {row}")

# 删除重复记录（保留 id 最小的那条）
cursor.execute("""
    DELETE FROM prompt_templates 
    WHERE id NOT IN (
        SELECT MIN(id) 
        FROM prompt_templates 
        GROUP BY prompt_type, prompt_key, scope, owner_user_id
    )
""")
print(f"删除了 {cursor.rowcount} 条重复记录")

conn.commit()
conn.close()
print("修复完成！")
EOF
```

#### 2. 执行脚本

```bash
python3 /tmp/fix_prompt.py
```

#### 3. 重启服务

```bash
cd /root/.openclaw/workspace/deep-reading-agent
bash start.sh
```

---

## 问题 2：上传文献时报错 "文件过大"

### 错误现象

修复问题 1 后，上传文献时前端报错"文件过大"，但实际文件不到 2MB。

### 排查过程

#### 1. 检查是否有 Nginx

```bash
grep -r "client_max_body_size" /etc/nginx/
```

结果为空，说明没有显式配置 `client_max_body_size`。

#### 2. 检查端口监听

```bash
ss -tlnp | grep ':80'
```

输出：

```
LISTEN 0  511  0.0.0.0:80  0.0.0.0:*  users:(("nginx",pid=3154757,fd=5),...)
```

发现 **Nginx 正在监听 80 端口**。

#### 3. 检查架构链路

```bash
cat /root/.cloudflared/config.yml
```

输出：

```
ingress:
  - hostname: deepreading.qzz.io
    service: http://127.0.0.1:80
```

确认架构：

```
Cloudflare Tunnel → Nginx (80) → FastAPI (8000)
```

### 根因分析

Nginx 的 `client_max_body_size` 默认值为 **1MB**，超过此大小的文件上传会被 Nginx 直接拒绝，返回 413 错误。

### 解决方案

#### 1. 找到 Nginx 配置文件

```bash
nginx -t
```

输出会显示配置文件路径，通常是 `/etc/nginx/nginx.conf`。

#### 2. 添加文件大小限制配置

```bash
vi /etc/nginx/nginx.conf
```

在 `http` 块中添加：

```
http {
    client_max_body_size 50m;
    ...
}
```

#### 3. 测试并重启 Nginx

```bash
nginx -t          # 测试配置语法
nginx -s reload   # 重新加载配置
```

---

## 问题 3：参考文献梳理时报错 `401 Authentication Fails`

### 错误现象

参考文献梳理功能报错：

```
❌ Error code: 401 - {'error': {'message': 'Authentication Fails, Your api key: ****5b25 is invalid', ...}}
```

用户已在前端配置了自己的 DeepSeek API Key，但系统仍使用服务器环境变量中的旧 Key（以 `5b25` 结尾）。

### 排查过程

#### 1. 检查服务器代码是否更新

```bash
cd /root/.openclaw/workspace/deep-reading-agent
git log --oneline -3
```

确认代码已是最新版本。

#### 2. 分析 API Key 传递链路

检查后端代码发现，API Key 传递链路在 `_try_extract_references` 处断裂：

```
前端用户 Key
    ↓
run_quant_task(api_key) / run_qual_task(api_key)
    ↓
_try_extract_references() ← 没有接收 api_key 参数 ❌
    ↓
extract_references_deepseek()
    ↓
call_deepseek_json() → os.getenv("DEEPSEEK_API_KEY") ← 使用环境变量 ❌
```

#### 3. 检查前端代码

发现 `ReferenceTraceTab` 组件没有接收和传递 `apiKey` 参数：

```javascript
// App.tsx
<ReferenceTraceTab />  // ← 没有传递 apiKey

// ReferenceTraceTab.tsx
body: JSON.stringify({})  // ← 没有包含 api_key
```

### 根因分析

问题有两层：

1. **后端**：`deepseek_refs.py` 中的 `call_deepseek_json` 直接使用 `os.getenv("DEEPSEEK_API_KEY")`，没有接受用户提供的 Key
2. **前端**：`ReferenceTraceTab` 组件没有接收父组件传递的 `apiKey`，也没有在请求中发送 `api_key`

### 解决方案

#### 1. 后端修复

修改 `backend/services/deepseek_refs.py`：

```python
# 修改前
def call_deepseek_json(messages, *, max_tokens, temperature):
    api_key = os.getenv("DEEPSEEK_API_KEY")

# 修改后
def call_deepseek_json(messages, *, max_tokens, temperature, api_key=None):
    if not api_key or not api_key.strip():
        api_key = os.getenv("DEEPSEEK_API_KEY")  # 回退到环境变量
```

同时修改 `extract_references_deepseek` 和 `trace_citations_deepseek` 函数，接收并传递 `api_key` 参数。

修改 `backend/routers/reading.py` 中的 `_try_extract_references` 函数，接收并传递 `api_key` 参数。

修改 `backend/routers/references.py` 中的 `run_reference_trace_task` 函数，接收并传递 `api_key` 参数。

#### 2. 前端修复

修改 `frontend/src/App.tsx`：

```jsx
// 修改前
<ReferenceTraceTab />

// 修改后
<ReferenceTraceTab apiKey={apiKey} />
```

修改 `frontend/src/ReferenceTraceTab.tsx`：

```tsx
// 修改前
export default function ReferenceTraceTab() {
  // ...
  body: JSON.stringify({})

// 修改后
export default function ReferenceTraceTab({ apiKey }: { apiKey: string }) {
  // ...
  body: JSON.stringify({ ...(apiKey ? { api_key: apiKey } : {}) })
```

#### 3. 提交并推送

```bash
git add backend/services/deepseek_refs.py backend/routers/reading.py backend/routers/references.py
git commit -m "fix: use user-provided API key for reference extraction"

git add frontend/src/App.tsx frontend/src/ReferenceTraceTab.tsx
git commit -m "fix: pass user API key to reference trace from frontend"

git push origin online
```

---

## 服务器架构总结

```
┌─────────────────────────────────────────────────────────────────┐
│                         请求链路                                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   用户浏览器                                                      │
│       │                                                         │
│       ▼                                                         │
│   Cloudflare Tunnel (HTTPS, 100MB 限制)                         │
│       │                                                         │
│       ▼                                                         │
│   Nginx (端口 80, 默认 1MB 限制)                                 │
│       │                                                         │
│       ▼                                                         │
│   FastAPI/Uvicorn (端口 8000)                                   │
│       │                                                         │
│       ▼                                                         │
│   SQLite 数据库                                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 常用排查命令

| 目的 | 命令 |
|------|------|
| 查看后端日志 | `tail -100 /tmp/fastapi.log` |
| 查看前端日志 | `tail -100 /tmp/vite.log` |
| 检查服务进程 | `ps aux \| grep -E "uvicorn\|vite\|cloudflared\|nginx"` |
| 检查端口监听 | `ss -tlnp` |
| 测试 Nginx 配置 | `nginx -t` |
| 重启 Nginx | `nginx -s reload` |
| 检查数据库重复记录 | 见问题 1 的修复脚本 |
| 查看错误日志 | `grep -i "error\|401\|authentication\|failed" /tmp/fastapi.log \| tail -20` |

---

## 预防措施

1. **数据库层面**：在 `prompt_templates` 表上添加唯一约束，防止重复记录
2. **Nginx 层面**：部署时确保配置 `client_max_body_size` 为合理值
3. **代码层面**：查询时使用 `LIMIT 1` 或 `first()` 代替 `scalar_one_or_none()`，避免多行结果导致异常
4. **API Key 层面**：所有使用 API Key 的模块都应优先使用用户提供的 Key，环境变量仅作为回退选项
5. **前端层面**：所有需要 API Key 的页面组件都应接收并传递 `apiKey` 参数
