import os
import re
import logging
from pdfminer.high_level import extract_text
from pdfminer.layout import LAParams
import PyPDF2

class PDFExtractor:
    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def extract_content(self, file_path):
        """
        Extracts text from a PDF file.
        Tries pdfminer first, falls back to PyPDF2.
        """
        text = ""
        try:
            # Try pdfminer first for better layout preservation
            laparams = LAParams()
            text = extract_text(file_path, laparams=laparams)
        except Exception as e:
            self.logger.warning(f"pdfminer failed for {file_path}: {e}. Trying PyPDF2.")
            try:
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        text += page.extract_text() + "\n"
            except Exception as e2:
                self.logger.error(f"PyPDF2 also failed for {file_path}: {e2}")
                # Placeholder for OCR fallback
                # if OCR_ENABLED:
                #     text = self._ocr_extract(file_path)
                return None

        return self._clean_text(text)

    # def _ocr_extract(self, file_path):
    #     import pytesseract
    #     from pdf2image import convert_from_path
    #     images = convert_from_path(file_path)
    #     text = ""
    #     for img in images:
    #         text += pytesseract.image_to_string(img)
    #     return text

    def _clean_text(self, text):
        if not text:
            return ""
        
        # Remove null bytes and other non-printable chars (except newline/tab)
        text = "".join(ch for ch in text if ch.isprintable() or ch in ['\n', '\t'])
        
        # 1. Fix hyphenation for English (e.g., "analy- sis" -> "analysis")
        text = re.sub(r'(\w+)-\s+(\w+)', r'\1\2', text)
        
        # 2. Remove spaces between Chinese characters (e.g., "研 究 背 景" -> "研究背景")
        # Pattern: Chinese char + whitespace + Chinese char -> remove whitespace
        text = re.sub(r'([\u4e00-\u9fa5])\s+([\u4e00-\u9fa5])', r'\1\2', text)
        # Repeat once more to handle multiple spaces or 3-char sequences better (simple heuristic)
        text = re.sub(r'([\u4e00-\u9fa5])\s+([\u4e00-\u9fa5])', r'\1\2', text)

        # 3. Remove multiple newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()
