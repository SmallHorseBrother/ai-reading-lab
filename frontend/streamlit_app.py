#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 学习系统 - Streamlit 前端
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import streamlit as st
from core.engine import LearningEngine
from core.llm_client import LLMError
from core.settings import library_dir, output_dir

DEFAULT_OUTPUT = str(output_dir())
DEFAULT_LIBRARY = str(library_dir())

st.set_page_config(page_title="AI 学习系统", page_icon="📚", layout="wide")


@st.cache_resource
def get_engine():
    return LearningEngine(DEFAULT_OUTPUT)


@st.cache_data(ttl=30)
def scan_library(library_path: str):
    """扫描资料库，返回所有可学习文件"""
    if not os.path.exists(library_path):
        return []

    results = []
    for root, dirs, files in os.walk(library_path):
        # 跳过进度/缓存目录
        dirs[:] = [d for d in dirs if d not in ("_学习进度", "cache", "__pycache__")]

        rel_root = os.path.relpath(root, library_path)
        if rel_root == ".":
            rel_root = ""

        for f in sorted(files):
            ext = Path(f).suffix.lower()
            if ext not in (".txt", ".docx", ".pdf"):
                continue
            full = os.path.join(root, f)
            size = round(os.path.getsize(full) / (1024*1024), 1)
            folder = rel_root if rel_root else "根目录"
            results.append({
                "name": Path(f).stem,
                "ext": ext,
                "folder": folder,
                "path": full,
                "size_mb": size,
            })
    return results


def init_session():
    defaults = {
        "course_id": None, "course_name": "", "chunks": [],
        "current_idx": 0, "mode": "book", "show_quiz": False,
        "quiz_content": "", "summary": "", "grading_result": None,
        "force_level": None,
        "summary_key": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def load_course_from_path(input_path: str):
    engine = get_engine()
    course_name, mode, chunks = engine.load_and_split(input_path)
    course_id = course_name.replace(" ", "_").replace("/", "_")
    st.session_state.course_id = course_id
    st.session_state.course_name = course_name
    st.session_state.mode = mode
    st.session_state.chunks = chunks
    st.session_state.current_idx = 0
    st.session_state.show_quiz = False
    st.session_state.grading_result = None
    st.session_state.force_level = None
    st.session_state.summary = ""
    st.session_state.summary_key = None
    st.session_state.quiz_content = ""
    st.session_state.answer_input = ""

    course = engine.store.get_course(course_id)
    saved_idx = course.get("current_index", 0)
    if 0 <= saved_idx < len(chunks):
        st.session_state.current_idx = saved_idx
    return course_name, len(chunks)


def render_sidebar():
    with st.sidebar:
        st.title("📚 AI 知识库")
        st.caption(f"资料目录：{DEFAULT_LIBRARY}")
        st.markdown("---")

        # 扫描资料库
        courses = scan_library(DEFAULT_LIBRARY)

        if not courses:
            st.info(f"📂 知识库为空\n\n请把 .txt / .docx / .pdf 文件放入：\n`{DEFAULT_LIBRARY}`")
        else:
            st.subheader(f"📖 发现 {len(courses)} 份资料")

            # 按文件夹分组显示
            by_folder = {}
            for c in courses:
                by_folder.setdefault(c["folder"], []).append(c)

            for folder, items in sorted(by_folder.items()):
                with st.expander(f"📁 {folder}", expanded=True):
                    for item in items:
                        icon = {".txt": "📄", ".docx": "📝", ".pdf": "📑"}.get(item["ext"], "📄")
                        size_str = f" {item['size_mb']}MB" if item['size_mb'] > 0 else ""
                        col1, col2 = st.columns([3, 2])
                        with col1:
                            st.write(f"{icon} **{item['name']}**{size_str}")
                        with col2:
                            if st.button("加载", key=f"load_{item['path']}", use_container_width=True):
                                with st.spinner("加载中..."):
                                    try:
                                        load_course_from_path(item['path'])
                                    except Exception as e:
                                        st.error(f"失败: {e}")

        st.markdown("---")

        # 当前课程信息
        if st.session_state.course_id:
            st.subheader("📌 当前课程")
            st.write(f"**{st.session_state.course_name}**")
            total = len(st.session_state.chunks)
            cur = st.session_state.current_idx + 1
            st.write(f"进度: {cur}/{total}")
            st.progress(min(1.0, st.session_state.current_idx / max(1, total - 1)))

            engine = get_engine()
            review = engine.get_review_status(st.session_state.course_id)
            if review["due_today"] > 0:
                st.warning(f"⏰ 今天复习: {review['due_today']} 个")
            else:
                st.success("✅ 无到期复习")

        st.markdown("---")
        with st.expander("💡 支持的格式"):
            st.markdown("""
            - **.txt** — 纯文本（推荐，最稳定）
            - **.docx** — Word 文档
            - **.pdf** — 文本型 PDF

            ⚠️ 扫描版 PDF（图片型）无法直接识别，
            请先转成 txt 或 docx 再放入知识库。
            """)


def render_main():
    if not st.session_state.course_id or not st.session_state.chunks:
        st.info("👈 请从左侧知识库选择一份资料加载")
        return

    engine = get_engine()
    course_id = st.session_state.course_id
    course_name = st.session_state.course_name
    mode = st.session_state.mode
    chunks = st.session_state.chunks
    idx = st.session_state.current_idx

    if idx >= len(chunks):
        st.balloons()
        st.success(f"🎉 已完成《{course_name}》全部 {len(chunks)} 个单元！")
        return

    chunk_name, content = chunks[idx]
    unit_id = f"u{idx}"
    course = engine.store.get_course(course_id)
    level = course.get("level", 2)

    # 导航栏
    c1, c2, c3 = st.columns([1, 4, 1])
    with c1:
        if st.button("⬅️ 上一单元", disabled=idx <= 0, use_container_width=True):
            st.session_state.current_idx = max(0, idx - 1)
            st.session_state.show_quiz = False
            st.session_state.grading_result = None
            st.session_state.force_level = None
            st.rerun()
    with c2:
        st.markdown(f"### 📄 {course_name} — 单元 {idx+1}/{len(chunks)}")
        st.caption(f"{chunk_name}  |  难度: **L{level}** ({['','极度浓缩','标准平衡','深度解剖'][level]})")
    with c3:
        if st.button("下一单元 ➡️", disabled=idx >= len(chunks) - 1, use_container_width=True):
            st.session_state.current_idx = min(len(chunks) - 1, idx + 1)
            st.session_state.show_quiz = False
            st.session_state.grading_result = None
            st.session_state.force_level = None
            st.rerun()

    st.markdown("---")

    tab1, tab2, tab3 = st.tabs(["📝 原文", "🤖 AI 总结", "✅ 随堂测评"])

    with tab1:
        st.text_area("原文", value=content, height=600, disabled=True, label_visibility="collapsed")

    with tab2:
        lc1, lc2, lc3, _ = st.columns([1, 1, 1, 3])
        display_level = st.session_state.get("force_level") or level
        with lc1:
            if st.button("⚡ L1 极度浓缩", type="primary" if display_level == 1 else "secondary", use_container_width=True):
                st.session_state.force_level = 1
                st.rerun()
        with lc2:
            if st.button("📊 L2 标准平衡", type="primary" if display_level == 2 else "secondary", use_container_width=True):
                st.session_state.force_level = 2
                st.rerun()
        with lc3:
            if st.button("🔬 L3 深度解剖", type="primary" if display_level == 3 else "secondary", use_container_width=True):
                st.session_state.force_level = 3
                st.rerun()

        summary_key = (course_id, unit_id, display_level)
        if st.session_state.summary_key != summary_key:
            st.session_state.summary = ""
        if st.button("生成 AI 总结", type="primary"):
            with st.spinner(f"生成 L{display_level}..."):
                try:
                    st.session_state.summary = engine.get_summary(course_id, unit_id, content, display_level, mode)
                    st.session_state.summary_key = summary_key
                except (LLMError, ValueError) as exc:
                    st.error(str(exc))
        if st.session_state.summary:
            st.markdown(st.session_state.summary)
        else:
            st.info("选择讲解深度后点击生成。生成内容会调用你配置的模型接口。")

    with tab3:
        if not st.session_state.show_quiz:
            st.info("先生成 AI 总结，再生成本单元的测评题。")
            if st.button("📝 生成测评题", type="primary", disabled=not st.session_state.summary):
                with st.spinner("出题中..."):
                    try:
                        quiz = engine.get_quiz(course_id, unit_id, st.session_state.summary, content, mode)
                        st.session_state.quiz_content = quiz
                        st.session_state.show_quiz = True
                        st.rerun()
                    except (LLMError, ValueError) as exc:
                        st.error(str(exc))
        else:
            st.markdown(st.session_state.quiz_content)
            st.markdown("---")

            if st.session_state.grading_result is None:
                answer = st.text_area("你的回答", height=200, key="answer_input")
                if st.button("提交答案", type="primary"):
                    if answer.strip():
                        with st.spinner("评分中..."):
                            try:
                                result = engine.submit_answer(
                                    course_id, unit_id, chunk_name,
                                    st.session_state.summary,
                                    st.session_state.quiz_content,
                                    answer
                                )
                                st.session_state.grading_result = result
                                st.rerun()
                            except (LLMError, ValueError) as exc:
                                st.error(str(exc))
                    else:
                        st.warning("请先输入回答")
            else:
                result = st.session_state.grading_result
                score = result["score"]
                sc, ic = st.columns([1, 3])
                with sc:
                    label = "优秀 🌟" if score >= 85 else ("良好 👍" if score >= 60 else "继续加油 💪")
                    st.metric("评分", f"{score}/100", label)
                with ic:
                    if result["old_level"] != result["new_level"]:
                        d = "降级（更精简）" if result["new_level"] < result["old_level"] else "升级（更详细）"
                        st.info(f"难度调整: L{result['old_level']} → L{result['new_level']} ({d})")
                    if result["review_scheduled"]:
                        st.warning("⏰ 已加入复习队列")

                with st.expander("查看详细评语"):
                    st.markdown(result["feedback"])

                course["current_index"] = idx + 1
                engine.store.update_course(course_id, course)

                b1, b2, b3 = st.columns(3)
                with b1:
                    if st.button("➡️ 下一单元", type="primary", use_container_width=True):
                        st.session_state.current_idx = idx + 1
                        st.session_state.show_quiz = False
                        st.session_state.grading_result = None
                        st.session_state.force_level = None
                        st.rerun()
                with b2:
                    if st.button("🔄 重新答", use_container_width=True):
                        st.session_state.grading_result = None
                        st.rerun()
                with b3:
                    if st.button("⏭️ 跳过", use_container_width=True):
                        st.session_state.current_idx = idx + 1
                        st.session_state.show_quiz = False
                        st.session_state.grading_result = None
                        st.session_state.force_level = None
                        st.rerun()


def main():
    init_session()
    render_sidebar()
    render_main()


if __name__ == "__main__":
    main()
