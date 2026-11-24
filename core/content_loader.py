#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
内容加载器：支持 txt, docx, pdf(文本型)
"""

import os
import re
from pathlib import Path
from typing import List, Tuple

HAS_FITZ = False
try:
    import fitz
    HAS_FITZ = True
except ImportError:
    pass

HAS_DOCX = False
try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    pass


def read_txt(path: str) -> str:
    for enc in ["utf-8", "utf-8-sig", "gbk", "gb2312", "big5"]:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    raise ValueError(f"无法识别编码: {path}")


def read_docx(path: str) -> str:
    if not HAS_DOCX:
        raise ImportError("未安装 python-docx: pip install python-docx")
    doc = Document(path)
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n".join(paragraphs)


def read_pdf(path: str) -> str:
    if not HAS_FITZ:
        raise ImportError("未安装 PyMuPDF: pip install PyMuPDF")
    doc = fitz.open(path)
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


def read_file(path: str) -> str:
    ext = Path(path).suffix.lower()
    if ext == ".txt":
        return read_txt(path)
    elif ext == ".docx":
        return read_docx(path)
    elif ext == ".pdf":
        return read_pdf(path)
    else:
        raise ValueError(f"不支持的文件格式: {ext}")


def collect_files(input_path: str, exclude_patterns: List[str] = None) -> List[str]:
    """
    收集输入路径下的所有支持文件
    支持单个文件或文件夹
    """
    if exclude_patterns is None:
        exclude_patterns = ["learning_system", "__pycache__", "cache", "汇总", "_report", "_处理报告"]

    p = Path(input_path)
    if p.is_file():
        return [str(p)]

    if p.is_dir():
        files = []
        for ext in ["*.txt", "*.docx", "*.pdf"]:
            for f in p.rglob(ext):
                # 排除匹配的文件/目录
                rel = str(f.relative_to(p))
                if any(pat in rel for pat in exclude_patterns):
                    continue
                files.append(str(f))
        return sorted(files)

    return []


def detect_mode(text: str, filename: str) -> str:
    """根据内容和文件名自动检测模式"""
    fn = filename.lower()

    if any(k in fn for k in ["视频", "文案", "transcript", "subtitle", "播客", "podcast"]):
        return "video"
    if any(k in fn for k in ["博主", "creator", "合集", "推文", "微博", "twitter"]):
        return "creator"
    if any(k in fn for k in ["文章", "article", "essay", "blog"]):
        return "article"

    chapter_patterns = [
        r"第[一二三四五六七八九十百零\d]+章",
        r"^\d+\.\s+",
        r"chapter\s+\d+",
        r"第[一二三四五六七八九十百零\d]+部分",
    ]
    if any(len(re.findall(pattern, text[:20000], re.I | re.M)) >= 2 for pattern in chapter_patterns):
        return "book"

    if re.search(r"\d{1,2}:\d{2}:\d{2}", text[:5000]) or text[:5000].count('"') > 20:
        return "video"

    if len(text) > 50000:
        return "book"
    return "article"


def load_course(input_path: str) -> Tuple[str, str, List[str]]:
    """
    加载课程内容
    返回: (course_name, detected_mode, list_of_file_paths)
    """
    p = Path(input_path)
    if p.is_file():
        course_name = p.stem
        text = read_file(str(p))
        mode = detect_mode(text, p.name)
        return course_name, mode, [str(p)]
    else:
        course_name = p.name
        files = collect_files(input_path)
        if not files:
            raise ValueError(f"未找到支持的文件: {input_path}")
        # 用第一个文件检测模式
        text = read_file(files[0])
        mode = detect_mode(text, files[0])
        return course_name, mode, files
