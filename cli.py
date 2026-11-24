#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 学习系统 - 命令行入口

用法：
  # 快速摄取（批量生成总结）
  python cli.py --input "examples/主动学习入门.txt" --mode book --preview

  # 交互学习（逐单元学习 + 测评 + 复习调度）
  python cli.py --input "examples/主动学习入门.txt" --mode book --study

  # 复习今天到期的内容
  python cli.py --input "examples/主动学习入门.txt" --review

  # 显示学习统计
  python cli.py --course "主动学习入门" --stats
"""

import os
import sys
import argparse
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from core.engine import LearningEngine
from core.llm_client import LLMError
from core.settings import output_dir

DEFAULT_OUTPUT = str(output_dir())


def print_banner():
    print("=" * 70)
    print("📚 AI Reading Lab")
    print("   快速摄取 + 自适应学习 + 间隔复习")
    print("=" * 70)


def cmd_batch(args):
    """批量处理模式：快速摄取"""
    engine = LearningEngine(args.output)
    result = engine.process_batch(args.input, mode=args.mode)

    course_id = result["course_id"]
    course_name = result["course_name"]

    # 保存终极总结
    out_dir = Path(args.output) / course_name
    out_dir.mkdir(parents=True, exist_ok=True)

    final_path = out_dir / "_终极总结.md"
    with open(final_path, "w", encoding="utf-8") as f:
        f.write(result["final_summary"])

    # 保存各单元总结
    for idx, (name, summary) in enumerate(result["summaries"]):
        sp = out_dir / "AI总结" / f"u{idx:02d}_summary.md"
        sp.parent.mkdir(parents=True, exist_ok=True)
        with open(sp, "w", encoding="utf-8") as f:
            f.write(f"# {name}\n\n{summary}\n")

    print(f"\n✅ 完成！")
    print(f"   课程: {course_name}")
    print(f"   模式: {result['mode']}")
    print(f"   单元数: {result['chunks_count']}")
    print(f"   终极总结: {final_path}")


def cmd_study(args):
    """交互学习模式"""
    engine = LearningEngine(args.output)
    course_name, mode, chunks = engine.load_and_split(args.input, args.mode)
    course_id = course_name.replace(" ", "_").replace("/", "_")
    course = engine.store.get_course(course_id)

    print_banner()
    print(f"\n📖 课程: {course_name}")
    print(f"   模式: {mode} | 单元数: {len(chunks)}")
    print(f"   当前难度: L{course.get('level', 2)}")

    start_idx = course.get("current_index", 0)
    for idx in range(start_idx, len(chunks)):
        chunk_name, content = chunks[idx]
        unit_id = f"u{idx}"
        level = course.get("level", 2)

        print(f"\n{'='*70}")
        print(f"📄 单元 {idx+1}/{len(chunks)}: {chunk_name}")
        print(f"   当前难度: L{level}")
        print(f"{'='*70}")

        # 1. 显示原文摘要（前500字）
        preview = content[:500].replace("\n", " ")
        print(f"\n📝 原文预览:\n{preview}...\n")
        input("按 Enter 查看 AI 总结...")

        # 2. 生成并显示摘要
        print(f"\n🤖 正在生成 L{level} 摘要...")
        summary = engine.get_summary(course_id, unit_id, content, level, mode)
        print(f"\n{'─'*70}")
        print(summary)
        print(f"{'─'*70}\n")
        input("按 Enter 开始测评...")

        # 3. 生成并显示题目
        print(f"\n📝 正在生成题目...")
        quiz = engine.get_quiz(course_id, unit_id, summary, content, mode)
        print(f"\n{'─'*70}")
        print(quiz)
        print(f"{'─'*70}\n")

        # 4. 用户作答
        print("请输入你的回答（多行输入，输入 END 结束）：")
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            except EOFError:
                break
        answer = "\n".join(lines)

        if not answer.strip():
            print("未作答，跳过本单元...")
            course["current_index"] = idx + 1
            engine.store.update_course(course_id, course)
            continue

        # 5. 评分
        print(f"\n🤖 正在评分...")
        result = engine.submit_answer(course_id, unit_id, chunk_name, summary, quiz, answer)

        print(f"\n{'='*70}")
        print(f"📊 评分结果: {result['score']}/100")
        if result['old_level'] != result['new_level']:
            direction = "降级（更精简）" if result['new_level'] < result['old_level'] else "升级（更详细）"
            print(f"   难度调整: L{result['old_level']} → L{result['new_level']} ({direction})")
        if result['review_scheduled']:
            print(f"   ⏰ 已加入复习队列")
        print(f"{'='*70}")
        print(f"\n💬 AI 评语:\n{result['feedback'][:1000]}")

        # 更新进度
        course["current_index"] = idx + 1
        engine.store.update_course(course_id, course)

        # 显示复习状态
        review_status = engine.get_review_status(course_id)
        if review_status["due_today"] > 0:
            print(f"\n⏰ 提醒: 今天有 {review_status['due_today']} 个复习单元到期")

        cont = input("\n继续下一个单元? (y/n/r=复习): ").strip().lower()
        if cont == "n":
            print("保存进度，下次继续...")
            break
        elif cont == "r":
            cmd_review_internal(engine, course_id, chunks)

    print(f"\n✅ 学习结束！当前进度: {course['current_index']}/{len(chunks)}")


def cmd_review_internal(engine, course_id, chunks):
    """内部复习逻辑"""
    due = engine.get_due_reviews(course_id, chunks)
    if not due:
        print("\n✅ 今天没有到期的复习单元")
        return

    print(f"\n⏰ 今天有 {len(due)} 个复习单元到期:\n")
    for idx, uid, name, content in due:
        print(f"  - {name}")

    for idx, uid, name, content in due:
        print(f"\n{'='*70}")
        print(f"🔁 复习: {name}")
        print(f"{'='*70}")

        course = engine.store.get_course(course_id)
        level = course.get("level", 2)
        summary = engine.get_summary(course_id, uid, content, level, "book")

        print(f"\n📝 原文预览:\n{content[:300].replace(chr(10), ' ')}...\n")
        input("按 Enter 查看摘要...")
        print(f"\n{summary[:1500]}\n")

        quiz = engine.get_quiz(course_id, uid, summary, content, "book")
        print(f"\n{quiz}\n")

        print("请输入你的回答（输入 END 结束）：")
        lines = []
        while True:
            try:
                line = input()
                if line.strip() == "END":
                    break
                lines.append(line)
            except EOFError:
                break
        answer = "\n".join(lines)

        if answer.strip():
            result = engine.submit_answer(course_id, uid, name, summary, quiz, answer)
            print(f"\n📊 评分: {result['score']}/100")
            print(result['feedback'][:800])


def cmd_review(args):
    """复习模式"""
    engine = LearningEngine(args.output)
    if args.input:
        course_name, mode, chunks = engine.load_and_split(args.input, args.mode)
        course_id = course_name.replace(" ", "_").replace("/", "_")
        cmd_review_internal(engine, course_id, chunks)
        return
    course_id = args.course.replace(" ", "_").replace("/", "_")
    print_banner()
    print(f"\n🔁 复习模式: {args.course}")

    review_status = engine.get_review_status(course_id)
    print(f"   复习项总数: {review_status['total_review_items']}")
    print(f"   已掌握: {review_status['mastered']}")
    print(f"   今天到期: {review_status['due_today']}")

    if review_status["due_today"] == 0:
        print("\n✅ 今天没有到期的复习单元")
        return

    print(f"\n到期单元: {', '.join(review_status['due_unit_ids'])}")
    print("提供 --input 原始资料路径可开始复习答题。")


def cmd_stats(args):
    """统计模式"""
    engine = LearningEngine(args.output)
    course_id = args.course.replace(" ", "_").replace("/", "_")
    course = engine.store.get_course(course_id)
    review_status = engine.get_review_status(course_id)

    print_banner()
    print(f"\n📊 课程统计: {args.course}")
    print(f"   当前进度: {course.get('current_index', 0)}")
    print(f"   当前难度: L{course.get('level', 2)}")
    print(f"   总学习次数: {len(course.get('history', []))}")
    if course.get('history'):
        scores = [h['score'] for h in course['history']]
        print(f"   平均得分: {sum(scores)/len(scores):.1f}")
        print(f"   最高分: {max(scores)} | 最低分: {min(scores)}")
    print(f"   复习项: {review_status['total_review_items']}")
    print(f"   已掌握: {review_status['mastered']}")
    print(f"   今天到期: {review_status['due_today']}")


def run():
    parser = argparse.ArgumentParser(description="AI Reading Lab：本地资料的主动学习与间隔复习")
    parser.add_argument("--input", "-i", help="输入文件或文件夹路径")
    parser.add_argument("--course", "-c", help="课程名称（用于复习/统计）")
    parser.add_argument("--mode", "-m", choices=["book", "video", "creator", "article"],
                        help="处理模式")
    parser.add_argument("--output", "-o", default=DEFAULT_OUTPUT, help="输出目录")
    parser.add_argument("--batch", action="store_true", help="批量快速摄取模式")
    parser.add_argument("--study", action="store_true", help="交互学习模式")
    parser.add_argument("--review", action="store_true", help="复习模式")
    parser.add_argument("--stats", action="store_true", help="统计模式")
    parser.add_argument("--preview", action="store_true", help="只预览解析结果，不调用模型或写入学习记录")
    args = parser.parse_args()
    if args.preview and args.input:
        from core.content_loader import load_course, read_file
        from core.splitter import split_content
        name, mode, files = load_course(args.input)
        units = [chunk for path in files for chunk in split_content(read_file(path), args.mode or mode)]
        print(f"资料：{name} | 模式：{args.mode or mode} | 单元：{len(units)}")
        for index, (title, text) in enumerate(units, 1):
            print(f"  {index}. {title} ({len(text)} 字符)")
    elif args.batch and args.input:
        cmd_batch(args)
    elif args.study and args.input:
        cmd_study(args)
    elif args.review and (args.course or args.input):
        cmd_review(args)
    elif args.stats and args.course:
        cmd_stats(args)
    elif args.input:
        # 默认批量模式
        cmd_batch(args)
    else:
        parser.print_help()


def main():
    try:
        run()
    except (LLMError, ValueError, OSError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
