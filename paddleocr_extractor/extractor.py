#!/usr/bin/env python3
"""
PaddleOCR PDF 提取器 - 独立模块
基于远程 Layout Parsing API，专为学术论文提取优化
"""

import os
import re
import base64
import requests
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Callable
from urllib.parse import urljoin

# 可选：加载 .env 文件
try:
    from dotenv import load_dotenv
    # 尝试加载模块目录的 .env
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        load_dotenv(env_path)
    # 尝试加载项目根目录的 .env (向上两级)
    project_env = Path(__file__).parent.parent / '.env'
    if project_env.exists():
        load_dotenv(project_env, override=False)  # 不覆盖已有变量
except ImportError:
    pass


class PaddleOCRPDFExtractor:
    """
    PaddleOCR PDF 提取器
    
    使用远程 Layout Parsing API 将 PDF 转换为 Markdown，
    自动提取论文中的插图，过滤公式/表格截图。
    
    Attributes:
        remote_url: API 端点地址
        remote_token: 访问令牌
        timeout: 请求超时时间（秒）
        only_original_images: 是否只保留论文原图
    """
    
    def __init__(
        self,
        remote_url: Optional[str] = None,
        remote_token: Optional[str] = None,
        timeout: int = 600,
        only_original_images: bool = True,
        use_table_recognition: bool = True,
        use_formula_recognition: bool = True,
        use_chart_recognition: bool = False,
        use_seal_recognition: bool = False,
        use_doc_orientation_classify: bool = False,
        use_doc_unwarping: bool = False,
        use_textline_orientation: bool = False,
        use_region_detection: bool = True,
        max_pages_per_chunk: int = 10,
        max_retries: int = 5,
        retry_interval: int = 10,
    ):
        """
        初始化提取器

        Args:
            remote_url: API 端点地址，默认从环境变量 PADDLEOCR_REMOTE_URL 读取
            remote_token: 访问令牌，默认从环境变量 PADDLEOCR_REMOTE_TOKEN 读取
            timeout: 请求超时时间（秒），默认 600
            only_original_images: 是否只保留论文原图，默认 True
            use_table_recognition: 启用表格识别（转 HTML/Markdown），默认 True
            use_formula_recognition: 启用公式识别（转 LaTeX），默认 True
            use_chart_recognition: 启用图表解析，默认 False
            use_seal_recognition: 启用印章识别，默认 False
            use_doc_orientation_classify: 启用文档方向矫正，默认 False
            use_doc_unwarping: 启用文档扭曲矫正，默认 False
            use_textline_orientation: 启用文本行方向矫正，默认 False
            use_region_detection: 启用版面区域检测，默认 True
            max_pages_per_chunk: 每次 API 调用最大页数，默认 10
            max_retries: API 调用最大重试次数，默认 5
            retry_interval: 重试间隔秒数，默认 10
        """
        self.remote_url = remote_url or os.getenv("PADDLEOCR_REMOTE_URL")
        self.remote_token = remote_token or os.getenv("PADDLEOCR_REMOTE_TOKEN")
        self.timeout = timeout
        self.only_original_images = only_original_images
        self.use_table_recognition = use_table_recognition
        self.use_formula_recognition = use_formula_recognition
        self.use_chart_recognition = use_chart_recognition
        self.use_seal_recognition = use_seal_recognition
        self.use_doc_orientation_classify = use_doc_orientation_classify
        self.use_doc_unwarping = use_doc_unwarping
        self.use_textline_orientation = use_textline_orientation
        self.use_region_detection = use_region_detection
        self.max_pages_per_chunk = max_pages_per_chunk
        self.max_retries = max_retries
        self.retry_interval = retry_interval
        
        if not self.remote_url or not self.remote_token:
            raise ValueError(
                "需要提供 remote_url 和 remote_token，"
                "或设置环境变量 PADDLEOCR_REMOTE_URL 和 PADDLEOCR_REMOTE_TOKEN"
            )
    
    def extract_pdf(
        self,
        pdf_path: str,
        out_dir: str = "output",
        download_images: bool = True,
        image_filter: Optional[Callable[[str], bool]] = None
    ) -> Dict:
        """
        提取 PDF 文件为 Markdown
        
        Args:
            pdf_path: PDF 文件路径
            out_dir: 输出目录
            download_images: 是否下载图片，默认 True
            image_filter: 自定义图片过滤函数，接收图片名返回是否保留
            
        Returns:
            {
                "markdown_path": Markdown 文件路径,
                "images_dir": 图片目录,
                "images": 图片列表,
                "stats": 统计信息
            }
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
        
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # 调用 API 提取
        print(f"正在提取: {pdf_path.name}")
        markdown_content, images = self._call_api(str(pdf_path))
        
        # 下载图片
        downloaded_images = {}
        if download_images and images:
            if image_filter:
                images = {k: v for k, v in images.items() if image_filter(k)}
            elif self.only_original_images:
                # 只保留论文原图（图1、图2等），过滤公式/表格/API中间图
                images = {
                    k: v for k, v in images.items() 
                    if "img_in_image_box" in k or "img_in_chart_box" in k
                }
            
            downloaded_images = self._download_images(images, out_dir)
            # 更新 markdown 中的图片路径
            markdown_content = self._update_image_paths(markdown_content, downloaded_images)
        
        # 保存 Markdown
        markdown_path = out_dir / f"{pdf_path.stem}_paddleocr.md"
        self._save_markdown(markdown_path, pdf_path.name, markdown_content)
        
        return {
            "markdown_path": str(markdown_path),
            "images_dir": str(out_dir / "imgs") if downloaded_images else None,
            "images": [
                {
                    "original_name": name,
                    "local_path": str(out_dir / local_path),
                    "size_kb": round((out_dir / local_path).stat().st_size / 1024, 2)
                }
                for name, local_path in downloaded_images.items()
            ],
            "stats": {
                "total_pages": markdown_content.count("## Page") + 1,
                "total_images": len(images),
                "downloaded_images": len(downloaded_images)
            }
        }
    
    def extract_text_only(self, pdf_path: str) -> Dict:
        """
        仅提取文本，不下载图片
        
        Args:
            pdf_path: PDF 文件路径
            
        Returns:
            {
                "title": 论文标题,
                "content": 完整 Markdown 文本,
                "abstract": 摘要,
                "keywords": 关键词列表,
                "sections": 章节列表
            }
        """
        pdf_path = Path(pdf_path)
        if not pdf_path.exists():
            raise FileNotFoundError(f"PDF 文件不存在: {pdf_path}")
        
        markdown_content, _ = self._call_api(str(pdf_path))
        
        # 解析基本信息
        title = self._extract_title(markdown_content)
        abstract = self._extract_abstract(markdown_content)
        keywords = self._extract_keywords(markdown_content)
        sections = self._extract_sections(markdown_content)
        
        return {
            "title": title,
            "content": markdown_content,
            "abstract": abstract,
            "keywords": keywords,
            "sections": sections
        }
    
    def _split_pdf_to_chunks(self, pdf_path: str) -> List[bytes]:
        """
        将 PDF 按 max_pages_per_chunk 切分为多个 PDF 字节块（内存操作）。
        若总页数不超过限制则返回原始文件字节。
        """
        from pypdf import PdfReader, PdfWriter
        from io import BytesIO

        reader = PdfReader(pdf_path)
        total = len(reader.pages)

        if total <= self.max_pages_per_chunk:
            with open(pdf_path, "rb") as f:
                return [f.read()]

        chunks = []
        for start in range(0, total, self.max_pages_per_chunk):
            end = min(start + self.max_pages_per_chunk, total)
            writer = PdfWriter()
            for i in range(start, end):
                writer.add_page(reader.pages[i])
            buf = BytesIO()
            writer.write(buf)
            chunks.append(buf.getvalue())
            print(f"  分片 {len(chunks)}: 第 {start+1}-{end} 页 (共 {total} 页)")

        return chunks

    def _call_api(self, pdf_path: str) -> Tuple[str, Dict[str, str]]:
        """调用远程 API 提取 PDF，自动对长文档分片处理"""
        chunks = self._split_pdf_to_chunks(pdf_path)

        all_markdown = []
        all_images = {}

        for idx, chunk_bytes in enumerate(chunks):
            if len(chunks) > 1:
                print(f"  正在调用 API: 分片 {idx+1}/{len(chunks)}")

            file_data = base64.b64encode(chunk_bytes).decode("ascii")
            md, imgs = self._call_api_single(file_data, 0)

            # 多分片时给图片 key 加前缀避免冲突
            if len(chunks) > 1:
                imgs = {f"chunk{idx}_{k}": v for k, v in imgs.items()}

            all_markdown.append(md)
            all_images.update(imgs)

        return "\n\n".join(all_markdown), all_images

    def _call_api_single(self, file_data_b64: str, file_type: int) -> Tuple[str, Dict[str, str]]:
        """单次 API 调用，失败时自动重试，返回 (markdown_text, images_dict)"""
        import time

        headers = {
            "Authorization": f"token {self.remote_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "file": file_data_b64,
            "fileType": file_type,
            "useDocOrientationClassify": self.use_doc_orientation_classify,
            "useDocUnwarping": self.use_doc_unwarping,
            "useTextlineOrientation": self.use_textline_orientation,
            "useChartRecognition": self.use_chart_recognition,
            "useTableRecognition": self.use_table_recognition,
            "useFormulaRecognition": self.use_formula_recognition,
            "useSealRecognition": self.use_seal_recognition,
            "useRegionDetection": self.use_region_detection,
        }

        last_error = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    self.remote_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                response.raise_for_status()
                break
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    print(f"  API 调用失败 (第 {attempt}/{self.max_retries} 次): {e}")
                    print(f"  {self.retry_interval}s 后重试...")
                    time.sleep(self.retry_interval)
                else:
                    print(f"  API 调用失败 (第 {attempt}/{self.max_retries} 次): {e}")
                    raise last_error

        result = response.json()
        layout_results = result["result"]["layoutParsingResults"]

        markdown_parts = []
        images = {}

        for i, res in enumerate(layout_results):
            if "markdown" in res and "text" in res["markdown"]:
                markdown_parts.append(res["markdown"]["text"])

                # 收集图片 (处理 dict 或 list 格式)
                if "images" in res["markdown"]:
                    img_data = res["markdown"]["images"]
                    if isinstance(img_data, dict):
                        images.update(img_data)
                    elif isinstance(img_data, list):
                        for item in img_data:
                            if isinstance(item, dict) and "name" in item and "url" in item:
                                images[item["name"]] = item["url"]
                            elif isinstance(item, str):
                                images[f"img_{i}_{len(images)}.jpg"] = item
                if "outputImages" in res:
                    out_imgs = res["outputImages"]
                    if isinstance(out_imgs, dict):
                        for name, url in out_imgs.items():
                            images[f"{name}_{i}.jpg"] = url
                    elif isinstance(out_imgs, list):
                        for j, item in enumerate(out_imgs):
                            if isinstance(item, dict) and "url" in item:
                                images[f"output_{i}_{j}.jpg"] = item["url"]
                            elif isinstance(item, str):
                                images[f"output_{i}_{j}.jpg"] = item

        return "\n\n".join(markdown_parts), images
    
    def _download_images(self, images: Dict[str, str], out_dir: Path) -> Dict[str, str]:
        """保存图片到本地，支持 Base64 和 URL 两种来源"""
        imgs_dir = out_dir / "imgs"
        imgs_dir.mkdir(parents=True, exist_ok=True)

        downloaded = {}
        print(f"正在保存 {len(images)} 张图片...")

        for img_name, img_value in images.items():
            try:
                # 清理文件名
                safe_name = img_name.replace("/", "_").replace("\\", "_")
                safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._-")
                if not safe_name:
                    safe_name = f"img_{len(downloaded)}.jpg"

                local_path = imgs_dir / safe_name

                if img_value.startswith(("http://", "https://")):
                    # URL 模式：HTTP 下载
                    resp = requests.get(img_value, timeout=30)
                    resp.raise_for_status()
                    img_data = resp.content
                else:
                    # Base64 模式：直接解码
                    img_data = base64.b64decode(img_value)

                with open(local_path, "wb") as f:
                    f.write(img_data)

                # 按 img_name (key) 映射，因为 markdown 中引用的是 key
                downloaded[img_name] = f"imgs/{safe_name}"

            except Exception as e:
                print(f"  [FAIL] {img_name}: {e}")

        print(f"成功保存 {len(downloaded)} 张图片")
        return downloaded
    
    def _update_image_paths(self, markdown: str, image_map: Dict[str, str]) -> str:
        """更新 markdown 中的图片路径（按 key 即原始引用名替换为本地路径）"""
        for original_ref, local_path in image_map.items():
            markdown = markdown.replace(original_ref, local_path)
        return markdown
    
    def _save_markdown(self, output_path: Path, pdf_name: str, content: str):
        """保存 Markdown 文件"""
        header = f"""---
title: {pdf_name}
source_pdf: {pdf_name}
extractor: paddleocr
extract_mode: remote_layout
extract_date: {datetime.now().isoformat()}
---

# {pdf_name}

*提取工具: PaddleOCR (远程 Layout Parsing API)*

## Text Content

"""
        
        output_path.write_text(header + content, encoding="utf-8")
        print(f"已保存: {output_path}")
    
    def _extract_title(self, content: str) -> str:
        """从内容中提取标题"""
        lines = content.split('\n')
        for line in lines[:10]:
            line = line.strip()
            if line and not line.startswith('#') and len(line) > 10:
                return line
        return "Unknown"
    
    def _extract_abstract(self, content: str) -> str:
        """提取摘要"""
        match = re.search(r'摘要[：:]\s*(.+?)(?=\n\n|关键词|中图分类号)', content, re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
    
    def _extract_keywords(self, content: str) -> List[str]:
        """提取关键词"""
        match = re.search(r'关键词[：:]\s*(.+?)(?=\n|中图分类号)', content)
        if match:
            keywords = match.group(1)
            return [k.strip() for k in re.split(r'[；;]', keywords) if k.strip()]
        return []
    
    def _extract_sections(self, content: str) -> List[Dict]:
        """提取章节结构"""
        sections = []
        pattern = r'##\s*([一二三四五六七八九十]+[、\.])\s*(.+?)(?=\n)'
        for match in re.finditer(pattern, content):
            sections.append({
                "number": match.group(1),
                "title": match.group(2).strip()
            })
        return sections


# 便捷函数
def extract_pdf(pdf_path: str, out_dir: str = "output", **kwargs) -> Dict:
    """快捷函数：提取 PDF"""
    extractor = PaddleOCRPDFExtractor()
    return extractor.extract_pdf(pdf_path, out_dir, **kwargs)


def extract_text(pdf_path: str) -> Dict:
    """快捷函数：仅提取文本"""
    extractor = PaddleOCRPDFExtractor()
    return extractor.extract_text_only(pdf_path)
