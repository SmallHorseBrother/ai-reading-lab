#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能分块器：支持多种分块策略
"""

import re
from typing import List, Tuple


def split_by_chapters(text: str) -> List[Tuple[str, str]]:
    """尝试按章节分割"""
    patterns = [
        re.compile(r"(^|\n)(第[一二三四五六七八九十百零\d]+章[\s\.、]*[^\n]{2,40})(\n|$)", re.MULTILINE),
        re.compile(r"(^|\n)(第[一二三四五六七八九十百零\d]+部分[\s\.、]*[^\n]{2,40})(\n|$)", re.MULTILINE),
        re.compile(r"(^|\n)(Chapter\s*\d+[\s\.\-]*[^\n]{2,40})(\n|$)", re.MULTILINE | re.I),
        re.compile(r"(^|\n)(\d+\.\s+[^\n]{2,60})(\n|$)", re.MULTILINE),
    ]

    best_splits = []
    for pat in patterns:
        matches = list(pat.finditer(text))
        if len(matches) >= 3:
            positions = [m.start() for m in matches]
            if positions[-1] - positions[0] > len(text) * 0.3:
                best_splits = matches
                break

    if not best_splits:
        return []

    chapters = []
    for i, m in enumerate(best_splits):
        title = m.group(2).strip()
        start = m.start()
        end = best_splits[i + 1].start() if i + 1 < len(best_splits) else len(text)
        content = text[start:end].strip()
        if len(content) > 300:
            chapters.append((title, content))
    return chapters


def split_by_size(text: str, chunk_size: int, overlap: int = 200) -> List[Tuple[str, str]]:
    """按固定字数分块"""
    chunks = []
    start = 0
    idx = 1
    while start < len(text):
        end = min(start + chunk_size, len(text))
        if end < len(text):
            para_end = text.rfind("\n\n", end - overlap, end)
            if para_end > end - overlap:
                end = para_end
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((f"逻辑块 {idx}", chunk))
            idx += 1
        start = end
    return chunks


def split_by_timestamps(text: str) -> List[Tuple[str, str]]:
    """按视频时间戳分割"""
    ts_pattern = re.compile(r"\n\d{1,2}:\d{2}:\d{2}\s+")
    matches = list(ts_pattern.finditer(text))
    if len(matches) >= 3:
        segments = []
        for i, m in enumerate(matches):
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            if len(content) > 100:
                ts = m.group().strip()
                segments.append((f"时间段 {ts}", content))
        if segments:
            return segments
    return []


def split_by_separators(text: str) -> List[Tuple[str, str]]:
    """按分隔符分割（用于creator/article合集）"""
    sep_patterns = [
        re.compile(r"\n={3,}\n"),
        re.compile(r"\n#{2,}\s+"),
        re.compile(r"\n\d{4}[年\-/]\d{1,2}[月\-/]\d{1,2}[日]?\s*\n"),
    ]
    for pat in sep_patterns:
        matches = list(pat.finditer(text))
        if len(matches) >= 3:
            segments = []
            for i, m in enumerate(matches):
                start = m.start()
                end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
                content = text[start:end].strip()
                if len(content) > 200:
                    preview = content[:40].replace("\n", " ")
                    segments.append((f"片段 {i+1}: {preview}...", content))
            if segments:
                return segments
    return []


def split_content(text: str, mode: str, chunk_size: int = 12000) -> List[Tuple[str, str]]:
    """根据模式智能分块"""
    if mode == "book":
        chapters = split_by_chapters(text)
        if chapters:
            return chapters
        return split_by_size(text, chunk_size)

    elif mode == "video":
        segs = split_by_timestamps(text)
        if segs:
            return segs
        return split_by_size(text, chunk_size)

    elif mode == "creator":
        segs = split_by_separators(text)
        if segs:
            return segs
        return split_by_size(text, chunk_size)

    else:  # article
        segs = split_by_separators(text)
        if segs:
            return segs
        return split_by_size(text, chunk_size)
