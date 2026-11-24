#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
学习引擎：核心编排器，串联所有模块
"""

import hashlib
from typing import List, Tuple, Dict, Any, Optional
from pathlib import Path

from .content_loader import load_course, read_file
from .splitter import split_content
from .ai_modules import generate_summary, generate_quiz, grade_answer, adjust_level
from .persistence import StateStore, Scheduler
from .llm_client import quick_chat
from .settings import model_name


class LearningEngine:
    def __init__(self, output_dir: str):
        self.store = StateStore(output_dir)
        self.scheduler = Scheduler()

    def _content_hash(self, text: str) -> str:
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:8]

    def load_and_split(self, input_path: str, mode: Optional[str] = None) -> Tuple[str, str, List[Tuple[str, str]]]:
        """
        加载并分块
        返回: (course_name, detected_mode, [(chunk_name, chunk_content), ...])
        """
        course_name, detected_mode, files = load_course(input_path)
        if mode:
            detected_mode = mode

        all_chunks = []
        for fpath in files:
            text = read_file(fpath)
            chunks = split_content(text, detected_mode)
            # 如果是多文件，给chunk名加上文件名前缀
            if len(files) > 1:
                fname = Path(fpath).stem
                chunks = [(f"[{fname}] {name}", content) for name, content in chunks]
            all_chunks.extend(chunks)

        return course_name, detected_mode, all_chunks

    def get_summary(self, course_id: str, unit_id: str, content: str, level: int, mode: str,
                    model: Optional[str] = None) -> str:
        """获取摘要（带缓存）"""
        content_hash = self._content_hash(content + model_name(model))
        cache_key = self.store.make_cache_key(course_id, unit_id, level, content_hash)
        cached = self.store.get_cache(cache_key)
        if cached:
            return cached

        summary = generate_summary(content, mode, level, model)
        self.store.set_cache(cache_key, summary)
        return summary

    def get_quiz(self, course_id: str, unit_id: str, summary: str, content: str, mode: str,
                 model: Optional[str] = None) -> str:
        """获取题目（带缓存）"""
        content_hash = self._content_hash(content + summary + model_name(model))
        cache_key = self.store.make_cache_key(course_id, unit_id, 0, content_hash) + "_quiz"
        cached = self.store.get_cache(cache_key)
        if cached:
            return cached

        quiz = generate_quiz(summary, content, mode, model)
        self.store.set_cache(cache_key, quiz)
        return quiz

    def submit_answer(self, course_id: str, unit_id: str, title: str,
                      summary: str, quiz: str, answer: str,
                      grade_model: Optional[str] = None) -> Dict[str, Any]:
        """提交答案，评分，调整难度，调度复习"""
        course = self.store.get_course(course_id)
        current_level = course.get("level", 2)

        # 评分
        score, feedback = grade_answer(summary, quiz, answer, model=grade_model)

        # 记录
        self.store.record_attempt(course_id, unit_id, score, current_level)
        self.store.append_note(course_id, unit_id, title, score, feedback)

        # 调整难度
        new_level = adjust_level(current_level, score)
        if new_level != current_level:
            course["level"] = new_level

        # 调度复习
        self.scheduler.schedule_review(course, unit_id, score)
        self.store.update_course(course_id, course)

        return {
            "score": score,
            "feedback": feedback,
            "old_level": current_level,
            "new_level": new_level,
            "review_scheduled": score < 70 or (unit_id in course.get("reviews", {})),
        }

    def get_review_status(self, course_id: str) -> Dict[str, Any]:
        """获取复习状态"""
        course = self.store.get_course(course_id)
        return self.scheduler.get_review_summary(course)

    def get_due_reviews(self, course_id: str, chunks: List[Tuple[str, str]]) -> List[Tuple[int, str, str, str]]:
        """获取今天到期的复习单元 (index, name, content)"""
        course = self.store.get_course(course_id)
        due_ids = self.scheduler.get_due_reviews(course)

        # unit_id 格式: u0, u1, ...
        result = []
        for uid in due_ids:
            if uid.startswith("u"):
                try:
                    idx = int(uid[1:])
                    if 0 <= idx < len(chunks):
                        result.append((idx, uid, chunks[idx][0], chunks[idx][1]))
                except:
                    pass
        return result

    def process_batch(self, input_path: str, mode: Optional[str] = None,
                      summary_model: Optional[str] = None) -> Dict[str, Any]:
        """
        批量处理模式（快速摄取）：
        加载 → 分块 → 生成L1/L2/L3摘要 → 生成终极总结
        不生成题目/不评分
        """
        course_name, detected_mode, chunks = self.load_and_split(input_path, mode)
        course_id = course_name.replace(" ", "_").replace("/", "_")

        summaries = []
        for idx, (chunk_name, content) in enumerate(chunks):
            unit_id = f"u{idx}"
            print(f"  [{course_name}] 处理 {chunk_name} ...")

            # 快速摄取模式只生成 L2（标准平衡），L1/L3 在学习时按需生成
            summary = self.get_summary(course_id, unit_id, content, 2, detected_mode, summary_model)
            summaries.append((chunk_name, summary))

        # 生成终极总结
        final_prompt = self._build_final_prompt(course_name, detected_mode, summaries)
        print(f"  [{course_name}] 生成终极总结...")
        final_summary = quick_chat(final_prompt, model=summary_model, max_tokens=6000)

        return {
            "course_id": course_id,
            "course_name": course_name,
            "mode": detected_mode,
            "chunks_count": len(chunks),
            "summaries": summaries,
            "final_summary": final_summary,
        }

    def _build_final_prompt(self, course_name: str, mode: str, summaries: List[Tuple[str, str]]) -> str:
        summaries_text = "\n\n".join([f"## {name}\n{summary[:1500]}" for name, summary in summaries])

        if mode == "book":
            return f"""你是一位顶级知识管理专家。请基于以下各章节总结，生成《{course_name}》全书的终极知识地图。

{summaries_text}

请输出：
1. 全书一句话核心 thesis
2. 核心框架图（用文本层级表示）
3. 作者的方法论清单（所有 actionable 建议汇总，按主题分类）
4. 金句 TOP 10
5. 对读者的直接应用建议（分：本周可做 / 3个月策略 / 长期原则）
6. 与其他经典著作的关联推荐（3-5本，说明为什么关联）

输出为 Markdown 格式，结构清晰。
"""
        elif mode == "video":
            return f"""你是一位知识管理专家。以下是多个视频/播客的提炼笔记，请生成一份"系列知识地图"。

系列：《{course_name}》

{summaries_text}

请输出：
1. 整个系列的核心主题线和演进逻辑
2. 知识框架图
3. 最值得回看的 TOP 5 及理由
4. 可复用的方法论清单
5. 缺失拼图
6. 个人学习路径建议

输出为 Markdown。
"""
        elif mode == "creator":
            return f"""你是一位顶级内容策略师。以下是某位创作者大量内容的萃取笔记，请生成"创作者方法论白皮书"。

创作者：《{course_name}》

{summaries_text}

请输出：
1. 核心世界观与独特立场
2. 原创概念词典
3. 思维工具箱
4. 内容版图全景图
5. 反常识洞察 TOP 10
6. 学习路径建议
7. 最适合解决哪类问题

输出为 Markdown。
"""
        else:
            return f"""你是一位资深编辑。以下是多篇文章的精读笔记，请生成主题知识地图。

合集：《{course_name}》

{summaries_text}

请输出：
1. 合集覆盖的主题领域和核心议题
2. 文章之间的关联网络
3. 最有价值的3-5篇及理由
4. 跨文章出现的方法论/共识/争议点
5. 阅读顺序建议

输出为 Markdown。
"""
