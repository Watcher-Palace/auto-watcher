from enum import Enum
from scripts.utils import pipeline
from scripts.utils.web import WebClient

CONFLICT_SENTINEL = "<!-- CONFLICT-UNRESOLVED"

FETCH_URL_TOOL = {
    "name": "fetch_url",
    "description": "Fetch the text content of a URL to gather additional information while writing.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "The URL to fetch"}
        },
        "required": ["url"],
    },
}


class WriterMode(Enum):
    FIRST_DRAFT = "first_draft"
    WAITING_FOR_REVIEW = "waiting_for_review"
    REVISION = "revision"


def detect_mode(date_str: str, index: int) -> WriterMode:
    draft = pipeline.latest_draft(date_str, index)
    if not draft:
        return WriterMode.FIRST_DRAFT
    review = pipeline.latest_review(date_str, index)
    if not review:
        return WriterMode.WAITING_FOR_REVIEW
    return WriterMode.REVISION


FIRST_DRAFT_SYSTEM = """You are a writer for a Chinese feminist news blog.
Write a complete blog post in Chinese following this exact template structure:

Front matter:
---
title: [post title]
date: [YYYY-MM-DD HH:MM:SS]
categories: [A/B/C/D/N based on severity]
tags:
- [relevant tags]
---

Sections (use ## for top-level, #### for 时间线 inside 概述):
## 概述
[Summary. Use #### 时间线 subsection if story spans multiple dates]

## 信息来源
[Format: 日期，来源。*标题*。链接]

Optional sections (include only if relevant):
## 前情
## 后续
## 舆论
### 微博词条
## 相关内容

Inline formatting:
- <font color="red">text</font> for emphasis
- <font color="blue">text</font> for latest updates
- <font color="grey">text</font> for verbatim quotes

Category scale: A=刑事/极恶劣, B=民事/较大, C=非官方/较小, D=个人, N=中立/待续
Special tags: PING=插眼等后续, TODO=还需查证

You have access to a fetch_url tool. Use it to look up additional facts or verify
information as needed while writing."""

REVISION_SYSTEM = FIRST_DRAFT_SYSTEM + """

You are REVISING an existing draft. You have:
1. The previous draft
2. The reviewer's comments (<!-- [REVIEWER]: ... --> annotations)
3. The user's own annotations (<!-- [USER]: ... --> annotations)

Apply reviewer suggestions UNLESS they conflict with user annotations.
If a conflict exists, prepend the draft with:
<!-- CONFLICT-UNRESOLVED
Reviewer said: [reviewer's point]
Your annotation says: [user's point]
Please resolve before publishing.
END-CONFLICT -->"""


def run_writer(date_str: str, index: int, claude, web=None) -> WriterMode:
    """
    Write or revise a draft. Returns the WriterMode used.
    Raises ValueError if mode is WAITING_FOR_REVIEW.
    If web is provided, Claude can fetch URLs via tool use while writing.
    """
    mode = detect_mode(date_str, index)

    if mode == WriterMode.WAITING_FOR_REVIEW:
        raise ValueError(
            f"Draft v1 exists for {date_str}-{index} but has not been reviewed yet. "
            "Run review first, or discard the draft to start fresh."
        )

    titles = pipeline.get_event_titles(date_str)
    title = titles.get(index, f"事件{index}")

    if mode == WriterMode.FIRST_DRAFT:
        content = _write_first_draft(date_str, index, title, claude, web)
    else:
        content = _write_revision(date_str, index, title, claude, web)

    out_path, v = pipeline.next_draft_path(date_str, index, title)
    out_path.write_text(content)
    return mode


def _write_first_draft(date_str: str, index: int, title: str, claude, web) -> str:
    research_file = pipeline.find_research_file(date_str, index)
    if not research_file:
        raise FileNotFoundError(f"No research file found for {date_str}-{index}")
    research = research_file.read_text()
    user_prompt = f"研究资料：\n\n{research}"
    return _call_claude(FIRST_DRAFT_SYSTEM, user_prompt, claude, web)


def _write_revision(date_str: str, index: int, title: str, claude, web) -> str:
    draft_path, _ = pipeline.latest_draft(date_str, index)
    review_path, _ = pipeline.latest_review(date_str, index)
    draft = draft_path.read_text()
    review = review_path.read_text()
    user_prompt = f"原稿：\n\n{draft}\n\n审阅意见：\n\n{review}"
    return _call_claude(REVISION_SYSTEM, user_prompt, claude, web)


def _call_claude(system: str, user_prompt: str, claude, web) -> str:
    """Single-turn if no web client; tool-use loop if web client provided."""
    if web is None:
        return claude.simple(system, user_prompt)

    messages = [{"role": "user", "content": user_prompt}]
    while True:
        resp = claude.chat(system, messages, tools=[FETCH_URL_TOOL])
        if resp.stop_reason == "end_turn":
            return resp.text
        # Handle tool calls
        messages.append({"role": "assistant", "content": resp.raw_content})
        tool_results = []
        for call in resp.tool_calls:
            if call.name == "fetch_url":
                url = call.input["url"]
                try:
                    html = web.fetch(url)
                    content = web.extract_text(html)[:3000]
                except WebClient.FetchError as e:
                    content = f"Failed to fetch {url}: {e}"
                tool_results.append(claude.make_tool_result(call, content))
        messages.append({"role": "user", "content": tool_results})
