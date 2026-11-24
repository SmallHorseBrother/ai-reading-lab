#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
持久化模块：状态存储 + 复习调度器
"""

import os
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any


# ===================== 状态存储 =====================
class StateStore:
    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.state_file = self.base_dir / "state.json"
        self.cache_dir = self.base_dir / "cache"
        self.notes_file = self.base_dir / "study_notes.md"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._state = self._load()

    def _load(self) -> Dict[str, Any]:
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                pass
        return {"courses": {}, "version": "3.0"}

    def _save(self):
        tmp = self.state_file.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._state, f, ensure_ascii=False, indent=2)
        os.replace(str(tmp), str(self.state_file))

    def get_course(self, course_id: str) -> Dict[str, Any]:
        if course_id not in self._state["courses"]:
            self._state["courses"][course_id] = {
                "current_index": 0,
                "level": 2,
                "history": [],
                "reviews": {},
                "created_at": datetime.now().isoformat(),
            }
        return self._state["courses"][course_id]

    def update_course(self, course_id: str, data: Dict[str, Any]):
        self._state["courses"][course_id].update(data)
        self._save()

    def record_attempt(self, course_id: str, unit_id: str, score: int, level: int):
        course = self.get_course(course_id)
        course["history"].append({
            "unit_id": unit_id,
            "score": score,
            "level": level,
            "timestamp": datetime.now().isoformat(),
        })
        self._save()

    def append_note(self, course_id: str, unit_id: str, title: str, score: int, feedback: str):
        with open(self.notes_file, "a", encoding="utf-8") as f:
            f.write(f"\n## {course_id} - {unit_id}: {title}\n")
            f.write(f"**评分**: {score}/100 | **时间**: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n")
            f.write(feedback)
            f.write("\n---\n")

    def get_cache(self, key: str) -> Optional[str]:
        cache_file = self.cache_dir / f"{key}.txt"
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                return f.read()
        return None

    def set_cache(self, key: str, content: str):
        cache_file = self.cache_dir / f"{key}.txt"
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(content)

    def make_cache_key(self, course_id: str, unit_id: str, level: int, content_hash: str = "") -> str:
        return f"{course_id}_{unit_id}_L{level}_{content_hash[:8]}"


# ===================== 复习调度器 =====================
class Scheduler:
    """间隔复习调度器"""
    def __init__(self, intervals: List[int] = None):
        self.intervals = intervals or [1, 3, 7, 14, 30]

    def schedule_review(self, course: Dict[str, Any], unit_id: str, score: int,
                        advance_threshold: int = 80, regress_threshold: int = 80):
        """
        根据分数安排复习
        """
        reviews = course.get("reviews", {})
        item = reviews.get(unit_id, {
            "next_review": None,
            "interval_index": -1,
            "history": [],
        })

        item["history"].append({"score": score, "time": datetime.now().isoformat()})

        if score < 70:
            item["mastered"] = False
            # 没掌握，1天后复习
            item["interval_index"] = 0
            item["next_review"] = (datetime.now() + timedelta(days=1)).isoformat()
        elif score >= advance_threshold:
            # 掌握了，推进到更长间隔
            idx = item["interval_index"] + 1
            if idx < len(self.intervals):
                item["mastered"] = False
                item["interval_index"] = idx
                item["next_review"] = (datetime.now() + timedelta(days=self.intervals[idx])).isoformat()
            else:
                # 完成所有间隔，标记为掌握
                item["next_review"] = None
                item["mastered"] = True
        else:
            item["mastered"] = False
            # 及格但没完全掌握，保持当前间隔或回退
            idx = max(0, item["interval_index"])
            if idx < len(self.intervals):
                item["next_review"] = (datetime.now() + timedelta(days=self.intervals[idx])).isoformat()

        reviews[unit_id] = item
        course["reviews"] = reviews

    def get_due_reviews(self, course: Dict[str, Any]) -> List[str]:
        """获取今天到期的复习单元"""
        reviews = course.get("reviews", {})
        due = []
        now = datetime.now()
        for unit_id, item in reviews.items():
            if item.get("mastered"):
                continue
            next_review = item.get("next_review")
            if next_review:
                try:
                    nr = datetime.fromisoformat(next_review)
                    if nr <= now:
                        due.append(unit_id)
                except:
                    due.append(unit_id)
        return due

    def get_review_summary(self, course: Dict[str, Any]) -> Dict[str, Any]:
        """获取复习统计"""
        reviews = course.get("reviews", {})
        total = len(reviews)
        mastered = sum(1 for v in reviews.values() if v.get("mastered"))
        due = self.get_due_reviews(course)
        return {
            "total_review_items": total,
            "mastered": mastered,
            "due_today": len(due),
            "due_unit_ids": due,
        }
