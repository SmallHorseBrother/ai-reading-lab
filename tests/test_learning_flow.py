import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import httpx
from openai import OpenAI
import pytest

from core.engine import LearningEngine
from core.llm_client import LLMError
from core.persistence import Scheduler
from core import llm_client

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "offline-test-credential")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://offline.test/v1")
    monkeypatch.setenv("OPENAI_MODEL", "offline-model")
    calls = []

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        system = body["messages"][0]["content"]
        if "评分" in system or "考官" in system:
            content = "指出了核心问题，但应用案例需要更具体。[SCORE] 65 [/SCORE]"
        elif "出题" in system or "教官" in system:
            content = "## 测评题\n请用一个新案例说明主动提取如何暴露理解漏洞。"
        else:
            content = "## 标准讲解\n先确定学习目标，再通过独立回忆、反馈和实践检验理解。"
        return httpx.Response(200, json={
            "id": "offline-response", "object": "chat.completion", "created": 1,
            "model": body["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
        })

    def client(**kwargs):
        return OpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handler)))

    monkeypatch.setattr(llm_client, "OpenAI", client)
    return calls


def test_preview_is_offline_and_does_not_create_learning_state(tmp_path):
    output = tmp_path / "not-created"
    result = subprocess.run([
        sys.executable, "cli.py", "--input", "examples/主动学习入门.txt",
        "--mode", "book", "--preview", "--output", str(output),
    ], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
       env={**os.environ, "PYTHONUTF8": "1"}, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "单元：3" in result.stdout
    assert "确定一个学习目标" in result.stdout
    assert not output.exists()


def test_learning_round_trip_persists_feedback_and_review(tmp_path, provider):
    engine = LearningEngine(str(tmp_path))
    name, mode, chunks = engine.load_and_split(str(ROOT / "examples/主动学习入门.txt"))
    assert mode == "book"
    assert len(chunks) == 3
    title, content = chunks[0]
    summary = engine.get_summary(name, "u0", content, 2, mode)
    assert engine.get_summary(name, "u0", content, 2, mode) == summary
    assert len(provider) == 1  # Reusing a unit does not charge for another request.
    quiz = engine.get_quiz(name, "u0", summary, content, mode)
    result = engine.submit_answer(name, "u0", title, summary, quiz, "先独立复述，再寻找原文证据。")
    assert result["score"] == 65
    assert result["review_scheduled"]
    restored = LearningEngine(str(tmp_path))
    course = restored.store.get_course(name)
    assert course["history"][0]["score"] == 65
    assert course["reviews"]["u0"]["next_review"]
    assert "65/100" in (tmp_path / "study_notes.md").read_text(encoding="utf-8")
    assert all(call["model"] == "offline-model" for call in provider)


def test_model_change_does_not_reuse_old_model_cache(tmp_path, provider, monkeypatch):
    engine = LearningEngine(str(tmp_path))
    engine.get_summary("course", "u0", "原创学习资料", 2, "book")
    monkeypatch.setenv("OPENAI_MODEL", "another-offline-model")
    engine.get_summary("course", "u0", "原创学习资料", 2, "book")
    assert [call["model"] for call in provider] == ["offline-model", "another-offline-model"]


def test_missing_credentials_are_not_cached_as_study_material(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "offline-model")
    engine = LearningEngine(str(tmp_path))
    with pytest.raises(LLMError, match="OPENAI_API_KEY"):
        engine.get_summary("course", "u0", "学习资料", 2, "book")
    assert list((tmp_path / "cache").iterdir()) == []


@pytest.mark.parametrize("feedback", ["本题涉及 40 个概念。", "[SCORE] 101 [/SCORE]", ""])
def test_invalid_grading_does_not_change_progress(tmp_path, feedback):
    engine = LearningEngine(str(tmp_path))
    with patch("core.ai_modules.quick_chat", return_value=feedback):
        with pytest.raises(LLMError, match="有效评分"):
            engine.submit_answer("course", "u0", "单元", "摘要", "问题", "回答")
    assert engine.store.get_course("course")["history"] == []
    assert not (tmp_path / "study_notes.md").exists()


def test_failed_recall_reopens_a_previously_mastered_unit():
    scheduler = Scheduler(intervals=[1])
    course = {}
    scheduler.schedule_review(course, "u0", 95)
    scheduler.schedule_review(course, "u0", 95)
    assert course["reviews"]["u0"]["mastered"]
    scheduler.schedule_review(course, "u0", 30)
    assert not course["reviews"]["u0"]["mastered"]
    assert course["reviews"]["u0"]["next_review"]


def test_multiple_documents_keep_distinct_unit_names(tmp_path):
    (tmp_path / "甲.txt").write_text("原创材料甲。" * 100, encoding="utf-8")
    (tmp_path / "乙.txt").write_text("原创材料乙。" * 100, encoding="utf-8")
    engine = LearningEngine(str(tmp_path / "results"))
    _, _, chunks = engine.load_and_split(str(tmp_path), "book")
    assert len(chunks) == 2
    assert any("[甲]" in title for title, _ in chunks)
    assert any("[乙]" in title for title, _ in chunks)


def test_docx_and_text_pdf_load(tmp_path):
    docx = pytest.importorskip("docx")
    fitz = pytest.importorskip("fitz")
    from core.content_loader import read_file
    word_path = tmp_path / "sample.docx"
    document = docx.Document()
    document.add_paragraph("原创文档解析样例")
    document.save(word_path)
    assert "原创文档" in read_file(str(word_path))
    pdf_path = tmp_path / "sample.pdf"
    with fitz.open() as pdf:
        page = pdf.new_page()
        page.insert_text((72, 72), "Original PDF parsing example")
        pdf.save(pdf_path)
    assert "Original PDF" in read_file(str(pdf_path))


def test_web_load_is_offline_then_can_study_and_submit(tmp_path, monkeypatch, provider):
    pytest.importorskip("streamlit")
    from streamlit.testing.v1 import AppTest
    monkeypatch.setenv("AI_OUTPUT_DIR", str(tmp_path))
    monkeypatch.setenv("AI_LIBRARY_DIR", str(ROOT / "examples"))
    app = AppTest.from_file(str(ROOT / "frontend/streamlit_app.py"), default_timeout=20).run()
    assert not app.exception
    next(button for button in app.button if button.label == "加载").click().run()
    assert not app.exception
    assert any("单元 1/3" in item.value for item in app.markdown)
    assert provider == []
    next(button for button in app.button if button.label == "生成 AI 总结").click().run()
    assert not app.exception
    assert len(provider) == 1
    next(button for button in app.button if button.label == "📝 生成测评题").click().run()
    assert not app.exception
    app.text_area(key="answer_input").set_value("通过主动回忆和新的应用案例检验理解。").run()
    next(button for button in app.button if button.label == "提交答案").click().run()
    assert not app.exception
    assert any(metric.value == "65/100" for metric in app.metric)
    assert len(provider) == 3
