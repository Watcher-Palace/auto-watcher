"""Persistent incremental state for the tracker.

Shape: {"uids": {uid: {"last_seen_id": str | None,
                       "pending": {"next_page": int} | None}}}

`last_seen_id` lets each run stop paginating as soon as it reaches posts it
has already processed; `pending` is a resume cursor left behind when a run
stops early (request budget exhausted or account-level rate limit).
"""
from __future__ import annotations
import json
from pathlib import Path

from src.utils.pipeline import PIPELINE

DEFAULT_STATE: dict = {"uids": {}}


def state_path() -> Path:
    return PIPELINE / ".tracker-state.json"


def load_state(path: Path | None = None) -> dict:
    p = path or state_path()
    if not p.exists():
        return json.loads(json.dumps(DEFAULT_STATE))
    return json.loads(p.read_text(encoding="utf-8"))


def save_state(state: dict, path: Path | None = None) -> None:
    p = path or state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
