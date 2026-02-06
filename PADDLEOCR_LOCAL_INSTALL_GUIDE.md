# PaddleOCR 本地部署指南

> 适用于 RTX 50 系列 (Blackwell 架构) GPU 的 PaddlePaddle + PaddleOCR 本地部署

## 硬件环境

| 项目 | 值 |
|------|-----|
| GPU | NVIDIA GeForce RTX 5070 Ti Laptop GPU |
| 架构 | Blackwell (sm_120) |
| 计算能力 | 12.0 |
| 显存 | 12 GB |
| 驱动版本 | 572.84 |

## 软件要求

| 组件 | 版本 |
|------|------|
| CUDA | **12.9** |
| cuDNN | 9.9 |
| Python | 3.9 / 3.10 / 3.11 / 3.12 |
| PaddlePaddle | 3.2.0+ (GPU 版) |
| PaddleOCR | 最新版 |

---

## 第一步：安装 CUDA 12.9

### 1.1 下载 CUDA Toolkit

访问 NVIDIA CUDA 下载页面：

```
https://developer.nvidia.com/cuda-12-9-0-download-archive
```

选择以下选项：
- Operating System: **Windows**
- Architecture: **x86_64**
- Version: **11** (Windows 11) 或 **10**
- Installer Type: **exe (local)** (推荐，约 3GB)

### 1.2 安装 CUDA

1. 运行下载的安装程序
2. 选择 **自定义安装**
3. 勾选以下组件：
   - [x] CUDA Toolkit 12.9
   - [x] CUDA Documentation (可选)
   - [x] Visual Studio Integration (如果安装了 VS)
4. 安装路径保持默认：`C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9`
5. 等待安装完成

### 1.3 验证 CUDA 安装

打开 PowerShell，运行：

```powershell
nvcc --version
```

预期输出：
```
nvcc: NVIDIA (R) Cuda compiler driver
Copyright (c) 2005-2024 NVIDIA Corporation
Built on ...
Cuda compilation tools, release 12.9, V12.9.xxx
```

如果提示找不到命令，需要手动添加环境变量：
```powershell
# 添加到 PATH（临时）
$env:PATH += ";C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin"

# 或永久添加（需要管理员权限）
[Environment]::SetEnvironmentVariable("PATH", $env:PATH + ";C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin", "Machine")
```

---

## 第二步：安装 cuDNN 9.9

### 2.1 下载 cuDNN

访问 NVIDIA cuDNN 下载页面（需要 NVIDIA 账号）：

```
https://developer.nvidia.com/cudnn-downloads
```

选择：
- Operating System: **Windows**
- Architecture: **x86_64**
- CUDA Version: **12**
- 下载 **Local Installer (Zip)**

### 2.2 安装 cuDNN

1. 解压下载的 zip 文件
2. 将解压后的文件复制到 CUDA 安装目录：

```powershell
# 假设 cuDNN 解压到 D:\Downloads\cudnn-windows-x86_64-9.9.0.xx_cuda12-archive

# 复制 bin 文件
Copy-Item "D:\Downloads\cudnn-windows-x86_64-*\bin\*" "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin\" -Force

# 复制 include 文件
Copy-Item "D:\Downloads\cudnn-windows-x86_64-*\include\*" "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\include\" -Force

# 复制 lib 文件
Copy-Item "D:\Downloads\cudnn-windows-x86_64-*\lib\x64\*" "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\lib\x64\" -Force
```

### 2.3 验证 cuDNN 安装

```powershell
# 检查 cudnn64_9.dll 是否存在
Test-Path "C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin\cudnn64_9.dll"
# 应返回 True
```

---

## 第三步：安装 PaddlePaddle GPU 版

### 3.1 激活虚拟环境

```powershell
cd D:\code\deepagent\deep-reading-agent
.\venv\Scripts\Activate.ps1
```

### 3.2 升级 pip

```powershell
python -m pip install --upgrade pip
```

### 3.3 安装 PaddlePaddle GPU 版 (CUDA 12.9)

```powershell
python -m pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
```

> 如果下载慢，可以先下载 wheel 文件再本地安装

### 3.4 验证 PaddlePaddle 安装

```powershell
python -c "import paddle; print(paddle.__version__); print('CUDA:', paddle.device.is_compiled_with_cuda()); paddle.utils.run_check()"
```

预期输出：
```
3.2.0
CUDA: True
PaddlePaddle is installed successfully! Let's start deep learning with PaddlePaddle now.
```

---

## 第四步：安装 PaddleOCR

### 4.1 安装 PaddleOCR

```powershell
pip install paddleocr
```

### 4.2 安装依赖（如缺失）

```powershell
pip install opencv-python pillow numpy
```

### 4.3 验证 PaddleOCR

```python
from paddleocr import PaddleOCR

# 初始化（首次运行会下载模型）
ocr = PaddleOCR(use_angle_cls=True, lang='ch', use_gpu=True)

# 测试
result = ocr.ocr('test.png', cls=True)
print(result)
```

---

## 第五步：安装 PP-Structure（版面分析）

PP-Structure 是 PaddleOCR 的版面分析模块，提供与远程 API 类似的功能。

### 5.1 安装

```powershell
pip install "paddleocr[structure]"
# 或
pip install paddlex
```

### 5.2 使用示例

```python
from paddleocr import PPStructure

# 初始化版面分析引擎
engine = PPStructure(
    table=True,           # 启用表格识别
    ocr=True,             # 启用 OCR
    show_log=True,
    use_gpu=True
)

# 分析 PDF/图片
result = engine('paper.pdf')

# 输出结构化结果
for page in result:
    for item in page:
        print(item['type'], item.get('text', '')[:100])
```

---

## 常见问题

### Q1: `nvcc` 命令找不到

确保 CUDA bin 目录在 PATH 中：
```powershell
$env:PATH += ";C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.9\bin"
```

### Q2: PaddlePaddle 安装后 `is_compiled_with_cuda()` 返回 False

可能安装了 CPU 版本，重新安装 GPU 版本：
```powershell
pip uninstall paddlepaddle paddlepaddle-gpu
python -m pip install paddlepaddle-gpu==3.2.0 -i https://www.paddlepaddle.org.cn/packages/stable/cu129/
```

### Q3: CUDA out of memory

减少批处理大小或使用较小的模型：
```python
ocr = PaddleOCR(use_gpu=True, gpu_mem=4000)  # 限制 GPU 内存为 4GB
```

### Q4: cuDNN 相关错误

确保 cuDNN 版本与 CUDA 版本匹配（CUDA 12.9 需要 cuDNN 9.x）

---

## 参考链接

- [PaddlePaddle 官方安装指南](https://www.paddlepaddle.org.cn/install/quick)
- [PaddleOCR GitHub](https://github.com/PaddlePaddle/PaddleOCR)
- [CUDA Toolkit 下载](https://developer.nvidia.com/cuda-toolkit-archive)
- [cuDNN 下载](https://developer.nvidia.com/cudnn-downloads)
- [NVIDIA Blackwell 兼容性指南](https://docs.nvidia.com/cuda/blackwell-compatibility-guide/)

---

## 后续：替换远程 API

安装完成后，可以修改项目代码，将远程 PaddleOCR API 替换为本地调用。参见项目中的 `paddleocr_extractor/` 目录。
