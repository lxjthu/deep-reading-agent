# Windows 打包版 Release 与 OSS 上传 Runbook

> 最近验证：2026-05-24。适用于发布 `DeepReadingAgent-Web.zip` Windows 打包版。

## 目标位置

- GitHub Release：`lxjthu/deep-reading-agent` 的最新正式 release，当前为 `v2.0.0`
- OSS bucket：`lxj-pdf-upload`
- OSS endpoint：`https://oss-cn-wuhan-lr.aliyuncs.com`
- OSS 对象目录：`releases/`
- 当前对象：`releases/DeepReadingAgent-Web-2026-05-24.zip`

## 准备产物

默认使用重新打包后的 zip：

```powershell
Get-Item dist-repack\DeepReadingAgent-Web.zip
```

建议记录校验值：

```powershell
python -c "import hashlib, pathlib; p=pathlib.Path('dist-repack/DeepReadingAgent-Web.zip'); print(hashlib.sha256(p.read_bytes()).hexdigest())"
```

2026-05-24 产物 SHA256：

```text
26584af4063a0206d10672c62ac32d9af65611f0155e8a24ab6e98f20a8131e3
```

## 上传到 GitHub Release

如果 `gh auth status` 显示未登录或 token 失效，先登录：

```powershell
gh auth login -h github.com -w --git-protocol https
```

如果 Windows 凭据存储没有保存 token，可在用户明确允许后临时使用：

```powershell
gh auth login -h github.com -w --git-protocol https --insecure-storage
```

上传到当前 release：

```powershell
gh release upload v2.0.0 "dist-repack\DeepReadingAgent-Web.zip#DeepReadingAgent-Web-2026-05-24.zip" --repo lxjthu/deep-reading-agent --clobber
```

核验：

```powershell
gh release view v2.0.0 --repo lxjthu/deep-reading-agent --json assets,url
```

临时使用 `--insecure-storage` 后，上传完成必须清理：

```powershell
gh auth logout -h github.com -u lxjthu
```

## 上传到阿里云 OSS

本机可复用 `%USERPROFILE%\.ossutilconfig`，其中需要包含：

```ini
[Credentials]
endpoint=https://oss-cn-wuhan-lr.aliyuncs.com
accessKeyID=...
accessKeySecret=...
```

用仓库脚本上传并生成 24 小时签名 URL：

```powershell
python scripts\upload_release_to_oss.py dist-repack\DeepReadingAgent-Web.zip --object releases/DeepReadingAgent-Web-2026-05-24.zip
```

验证签名 URL 可下载：

```powershell
python -c "import requests; url='<SIGNED_URL>'; r=requests.get(url, headers={'Range':'bytes=0-0'}, timeout=30); print(r.status_code, r.headers.get('Content-Range'), r.headers.get('Content-Type'))"
```

预期返回：

```text
206 bytes 0-0/<file-size> application/zip
```

注意：如果签名 URL 是按 `GET` 方法生成的，直接用 `HEAD` 验证会返回 `403`，这是正常的。

## 更新线上下载入口

P11 方案选择的是后端动态生成短期 OSS 签名 URL，不把长期链接硬编码到前端。换包时只需要：

1. 上传新 zip 到 `releases/`，文件名带日期或版本。
2. 更新服务器环境变量：

```text
ALIYUN_OSS_APP_OBJECT=releases/DeepReadingAgent-Web-2026-05-24.zip
```

3. 重启后端，使 `GET /api/download-app/windows` 返回新对象的短期签名 URL。

