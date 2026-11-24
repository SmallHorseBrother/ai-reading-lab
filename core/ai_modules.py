#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 核心模块：三级摘要、出题器、评分器
"""

import re
from typing import List, Tuple, Optional
from .llm_client import quick_chat, LLMError


# ===================== 三级摘要生成器 =====================
SUMMARY_TEMPLATES = {
    "book": {
        1: """你是一位金牌商业教练。请对以下书籍内容进行【极度浓缩】总结。
要求：
- 只保留核心公理、公式、可直接执行的动作
- 删除所有案例、故事、修辞
- 用 bullet points，每条不超过20字
- 输出控制在500字以内

内容：
{content}
""",
        2: """你是一位金牌商业教练。请对以下书籍内容进行【标准平衡】总结。
要求：
1. 核心观点：3-5句话概括
2. 关键概念：列出重要概念，一句话解释
3. Actionable建议：可直接执行的行动清单
4. 金句摘录：3-5句最有冲击力的话
5. 批判性思考：2-3个值得思考的问题

内容：
{content}
""",
        3: """你是一位金牌商业教练。请对以下书籍内容进行【深度解剖】总结。
要求：
1. 核心论点及完整推导逻辑链
2. 关键概念的定义、边界条件、反面案例
3. 作者的思维路径和隐含的假设
4. 场景假设：如果条件变化，结论是否仍然成立
5. 与主流观点的冲突点和论证
6. 可直接执行的行动清单 + 执行中的常见陷阱

内容：
{content}
""",
    },
    "video": {
        1: """你是一位知识萃取专家。请对以下视频文案进行【极度浓缩】提炼。
要求：
- 一句话核心论点
- 5-8个关键信息点（每条不超过15字）
- 1-2个可直接执行的动作
- 删除所有铺垫、案例、情绪表达

内容：
{content}
""",
        2: """你是一位知识萃取专家。请对以下视频文案进行【标准平衡】提炼。
要求：
1. 一句话核心论点
2. 关键信息点（5-8个）
3. 可复用的方法论/框架
4. 适合什么场景回看
5. 相关延展（提到的书/人/概念）
6. 个人实践建议（1-3件事）

内容：
{content}
""",
        3: """你是一位知识萃取专家。请对以下视频文案进行【深度解剖】提炼。
要求：
1. 核心论点的完整推导过程和隐含假设
2. 方法论的具体步骤、边界条件、失败案例
3. 主讲人的论证风格和说服技巧分析
4. 如果听众背景不同，哪些建议需要调整
5. 与其他类似观点的对比和冲突
6. 深度实践指南 + 常见误区预警

内容：
{content}
""",
    },
    "creator": {
        1: """你是一位顶级内容策略师。请对以下内容进行【极度浓缩】的方法论萃取。
要求：
- 这位创作者最核心的3个信念
- 所有原创概念（每个一句话）
- 最可复用的1个框架（极简版）
- 输出控制在400字以内

内容：
{content}
""",
        2: """你是一位顶级内容策略师。请对以下内容进行【标准平衡】的方法论萃取。
要求：
1. 核心世界观和独特立场
2. 原创概念词典（每个概念一句话解释）
3. 可复用框架（含步骤和适用场景）
4. 反常识洞察
5. 表达方式特征
6. 内容版图地图（如果做成课程怎么划分）

内容：
{content}
""",
        3: """你是一位顶级内容策略师。请对以下内容进行【深度解剖】的方法论萃取。
要求：
1. 创作者的知识体系完整结构和底层逻辑
2. 每个原创概念的来源、演化、边界条件
3. 框架的假设前提、适用场景、失效条件
4. 创作者的论证模式、修辞策略、叙事结构深度分析
5. 与同行的差异化和竞争优势来源
6. 如果要系统学习这位创作者，完整的学习路径设计

内容：
{content}
""",
    },
    "article": {
        1: """你是一位资深编辑。请对以下文章进行【极度浓缩】总结。
- 一句话核心论点
- 3-5个关键信息点
- 1个可执行 takeaway

内容：
{content}
""",
        2: """你是一位资深编辑。请对以下文章进行【标准平衡】总结。
1. 核心论点
2. 关键证据/案例
3. 新概念/新视角
4. 可执行 takeaway
5. 文章质量评估（信息密度、论证严谨度）

内容：
{content}
""",
        3: """你是一位资深编辑。请对以下文章进行【深度解剖】总结。
1. 核心论点的论证链条和隐含假设
2. 证据的强度评估（有无选择性偏差、样本问题）
3. 新概念的定义、来源、与现有概念的差异
4. 如果作者的前提不成立，结论会如何变化
5. 文章的真正贡献和局限
6. 深度实践建议 + 批判性视角

内容：
{content}
""",
    },
}


def generate_summary(content: str, mode: str, level: int, model: Optional[str] = None) -> str:
    """生成三级摘要"""
    tmpl = SUMMARY_TEMPLATES.get(mode, SUMMARY_TEMPLATES["article"]).get(level, SUMMARY_TEMPLATES["article"][2])
    prompt = tmpl.format(content=content[:15000])  # 截断防超限
    system = "你是一个专业的知识萃取专家，输出结构化 Markdown。"
    return quick_chat(prompt, system=system, model=model, max_tokens=4096)


# ===================== 出题器 =====================
QUIZ_TEMPLATES = {
    "book": """你是一位严厉的教官。基于以下总结和原文，生成5道深度测评题。

要求：
- 第1-2题：逻辑理解题（考察对核心论点的理解）
- 第3-4题：应用题（给定场景，要求运用书中方法分析）
- 第5题：批判思考题（要求质疑或延伸作者观点）
- 每题标明分值（总分100分）
- 附参考答案要点（供评分用）

输出格式：
## 测评题

### Q1. [题型] 题目内容（xx分）
...

### 参考答案
1. ...
2. ...

---

总结：
{summary}

原文片段：
{content}
""",
    "video": """你是一位严厉的教官。基于以下视频文案提炼，生成5道测评题。

要求：
- 第1-2题：信息提取题（考察关键信息点）
- 第3-4题：方法论应用题（给定场景运用方法）
- 第5题：延伸思考题（如果条件变化怎么做）
- 每题标明分值（总分100分）
- 附参考答案要点

提炼内容：
{summary}

原文片段：
{content}
""",
    "creator": """你是一位严厉的教官。基于以下创作者方法论萃取，生成5道测评题。

要求：
- 第1-2题：概念理解题（考察对原创概念的理解）
- 第3-4题：框架应用题（用ta的框架分析给定问题）
- 第5题：创新题（如果你是这位创作者，会如何改进某个观点）
- 每题标明分值（总分100分）
- 附参考答案要点

萃取内容：
{summary}

原文片段：
{content}
""",
    "article": """你是一位严厉的教官。基于以下文章总结，生成5道测评题。

要求：
- 第1-2题：理解题
- 第3-4题：应用题
- 第5题：批判思考题
- 每题标明分值（总分100分）
- 附参考答案要点

总结：
{summary}

原文片段：
{content}
""",
}


def generate_quiz(summary: str, content: str, mode: str, model: Optional[str] = None) -> str:
    """生成测评题"""
    tmpl = QUIZ_TEMPLATES.get(mode, QUIZ_TEMPLATES["article"])
    prompt = tmpl.format(summary=summary[:5000], content=content[:8000])
    system = "你是一个严格的教官，出题要精准考察理解深度，不要太简单。"
    return quick_chat(prompt, system=system, model=model, max_tokens=4096)


# ===================== 评分器 =====================
GRADING_TEMPLATE = """你是一位严苛的考官。请对学员的回答进行评分。

评分标准：
- 理解准确（40分）：是否正确理解核心概念
- 应用恰当（30分）：是否能将知识应用到场景中
- 思考深度（20分）：是否有自己的见解和延伸
- 表达清晰（10分）：逻辑是否清晰、语言是否准确

要求：
1. 先给出详细评语，指出优点和不足
2. 最后必须输出分数标签：[SCORE] 数字 [/SCORE]
3. 分数范围 0-100

---

原内容总结：
{summary}

题目：
{quiz}

学员回答：
{answer}
"""


def grade_answer(summary: str, quiz: str, answer: str, model: Optional[str] = None) -> Tuple[int, str]:
    """
    评分
    返回: (score_int, full_feedback_text)
    """
    prompt = GRADING_TEMPLATE.format(summary=summary[:3000], quiz=quiz[:3000], answer=answer)
    system = "你是一位严苛但公正的考官。必须输出 [SCORE] 数字 [/SCORE] 标签。"
    feedback = quick_chat(prompt, system=system, model=model, max_tokens=2048)

    # 提取分数
    match = re.search(r"\[SCORE\]\s*(\d+)\s*\[/SCORE\]", feedback)
    if not match or not 0 <= int(match.group(1)) <= 100:
        raise LLMError("模型未返回有效评分，本次回答未写入进度，请重试。")
    score = int(match.group(1))
    return score, feedback


def adjust_level(current_level: int, score: int, downgrade_threshold: int = 85, upgrade_threshold: int = 60) -> int:
    """根据分数调整难度等级"""
    if score >= downgrade_threshold and current_level > 1:
        return current_level - 1
    elif score < upgrade_threshold and current_level < 3:
        return current_level + 1
    return current_level
