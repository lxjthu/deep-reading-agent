<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>{value_1}</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 100px auto; text-align: center; color: #374151; }
        .icon { font-size: 64px; margin-bottom: 20px; }
        .download-btn { background: #059669; color: white; padding: 12px 24px; border-radius: 8px; text-decoration: none; display: inline-block; margin-top: 20px; }
        .download-btn:hover { background: #047857; }
    </style>
</head>
<body>
    <div class="icon">📎</div>
    <h1>{value_2}</h1>
    <p>此文件类型不支持在线预览，请下载后查看。</p>
    <a href="/api/download/{value_3}" download class="download-btn">⬇ 下载文件</a>
</body>
</html>