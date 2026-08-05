from __future__ import annotations
import re
import shutil
import subprocess
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.pipeline import REPO_ROOT, PIPELINE
from src.utils import ledger
from src.utils.archive import finalize_event


PIPELINE_COMMENT_RE = re.compile(r"<!--\s*\[(USER|REVIEWER|WRITER-)")


def check_review_resolved(date_str: str, n: int) -> None:
    """发布前置检查：最新评审（若存在）必须全部处置且无 未解决。"""
    from src.utils.pipeline import latest_review
    lr = latest_review(date_str, n)
    if lr is None:
        return
    from src.review_linter import check_dispositions
    violations, unresolved = check_dispositions(lr[0].read_text(encoding="utf-8"))
    problems = violations + (["存在 未解决 处理项"] if unresolved else [])
    if problems:
        raise SystemExit(
            f"评审 {lr[0].name} 未完全处置，拒绝发布：\n"
            + "\n".join(f"  - {p}" for p in problems))


def read_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    end = content.index("---", 3)
    return yaml.safe_load(content[3:end]) or {}


def load_tag_registry() -> set[str]:
    registry_path = Path(__file__).parent / "tags.yml"
    if not registry_path.exists():
        return set()
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    allowed: set[str] = set()
    for group in data.values():
        if isinstance(group, list):
            allowed.update(group)
    return allowed


def load_tag_group(group: str) -> set[str]:
    """Tags of one group in tags.yml (e.g. 'charge'). Empty set if absent."""
    registry_path = Path(__file__).parent / "tags.yml"
    if not registry_path.exists():
        return set()
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    value = data.get(group)
    return set(value) if isinstance(value, list) else set()


def validate_tags(tags, registry: set[str]) -> None:
    if not registry:
        return
    unknown = [t for t in (tags or []) if t not in registry]
    if unknown:
        raise SystemExit(
            f"Unknown tags {unknown}. Add to src/tags.yml or remove from draft."
        )


def copy_draft(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def move_assets(src: Path, dst: Path, keep: set[str] | None = None) -> None:
    """把 src 目录里的资产**并入** dst，与 dst 既有文件平铺同级。

    不能直接 `shutil.move(src, dst)`：dst 已存在为目录时那是"移进去"，会得到
    `dst/<src 目录名>/图.jpg` 套一层的结构，而 Hexo 的 `asset_path` 只在文章资产
    目录根下找同名文件，套一层就渲染成空 `src`。dst 已存在是常规情形——手工放进去的
    文书附件，或对同一事件重跑发布。

    `keep` 给定时只搬集合内的文件名（＝正文 `{% asset_path %}` 引用到的），其余留在
    原地、由 finalize_event 归档。研究阶段"照抓不筛"、写作阶段裁掉的证据图常涉隐私
    （伤情照、未打码文书），整目录搬运会把它们连同文章一起推上 gh-pages——正文虽不
    链接，URL 却是公开可访问的。（用户裁定 2026-08-05，260721-3 已发生一次。）
    """
    if not src.exists():
        return
    for item in sorted(src.iterdir()):
        if keep is not None and item.name not in keep:
            continue
        dst.mkdir(parents=True, exist_ok=True)
        shutil.move(str(item), str(dst / item.name))
    if not any(src.iterdir()):
        src.rmdir()


def check_todo_tag(tags, allow_todo: bool) -> None:
    """TODO = 我们的调查没做完（不是事件没进展），默认拒绝发布。"""
    if "TODO" in (tags or []) and not allow_todo:
        raise SystemExit(
            "草稿挂 TODO（待查证）——本站调查未完成，拒绝发布。\n"
            "  查证完成/存疑内容已删除 → 从 frontmatter 移除 TODO 后重跑；\n"
            "  事件本身待后续进展 → 该用 PING，不是 TODO；\n"
            "  确需带 TODO 上线 → 加 --allow-todo 显式放行。"
        )


def publish(date_str: str, n: int, title: str, draft_path: Path, deploy: bool = True,
            allow_todo: bool = False) -> None:
    if ledger.get_row(date_str, n) is None:
        raise SystemExit(
            f"账本中无 {date_str}-{n} 行——先运行 python src/pipeline_cli.py add {date_str} {n} <标题>"
        )
    content = draft_path.read_text(encoding="utf-8")
    fm = read_frontmatter(content)
    validate_tags(fm.get("tags"), load_tag_registry())
    check_todo_tag(fm.get("tags"), allow_todo)
    from src.linter import TAG_PROPOSAL_RE
    proposals = TAG_PROPOSAL_RE.findall(content)
    if proposals:
        raise SystemExit(
            "未裁决的 [TAG-PROPOSAL]，拒绝发布：\n"
            + "\n".join(f"  - {p}" for p in proposals)
            + "\n批准：将标签加入 src/tags.yml 相应分组和草稿 frontmatter，删除注释；"
              "否决：删除注释。"
        )
    if PIPELINE_COMMENT_RE.search(content):
        raise SystemExit(
            "草稿含未消费的流程注释（[USER]/[REVIEWER]/[WRITER-*]），拒绝发布")
    check_review_resolved(date_str, n)
    from src.linter import lint_text, lint_warnings
    from datetime import date as _date
    violations = lint_text(content, load_tag_registry(), _date.today())
    if violations:
        raise SystemExit(
            "Draft fails lint:\n" + "\n".join(f"  - {v}" for v in violations)
        )
    for w in lint_warnings(content):
        print(f"  ~ LINT WARN: {w}")
    posts_dir = REPO_ROOT / "source" / "_posts"
    post_slug = ledger.post_slug(date_str, n)

    copy_draft(draft_path, posts_dir / f"{post_slug}.md")
    print(f"Copied draft → {posts_dir / f'{post_slug}.md'}")

    assets_src = PIPELINE / "draft" / f"{date_str}-{n}-assets"
    from src.linter import ASSET_REF_RE
    referenced = {m.group(1).strip().strip("\"'") for m in ASSET_REF_RE.finditer(content)}
    skipped = sorted(p.name for p in assets_src.iterdir()
                     if p.name not in referenced) if assets_src.is_dir() else []
    move_assets(assets_src, posts_dir / post_slug, keep=referenced)
    if (posts_dir / post_slug).exists():
        print(f"Moved assets → {posts_dir / post_slug}")
    for name in skipped:
        print(f"  ~ 未引用，不发布（留待归档）：{name}")

    # The landing-page calendar is generated at build time by
    # scripts/calendar.js from post frontmatter — no manual injection needed.

    if deploy:
        subprocess.run(["pnpm", "run", "build"], cwd=REPO_ROOT, check=True)
        subprocess.run(["pnpm", "run", "deploy"], cwd=REPO_ROOT, check=True)
        print("Deployed to GitHub Pages")

    ledger.record_published(date_str, n, pub_title=str(fm.get("title", title)))
    print(f"Recorded {date_str}-{n} as published in events.csv (经验提取=待提取)")

    if finalize_event(date_str, n):
        print(f"Date {date_str} complete → archived to _pipeline_archive/")
    else:
        print(f"Event {date_str}-{n} artifacts archived to _pipeline_archive/")


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    import sys as _sys
    args = [a for a in _sys.argv[1:] if not a.startswith("--")]
    allow_todo = "--allow-todo" in _sys.argv[1:]
    date_str = args[0]
    n = int(args[1])
    drafts = sorted(
        (PIPELINE / "draft").glob(f"{date_str}-{n}-*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not drafts:
        print(f"No draft found for {date_str}-{n}")
        _sys.exit(1)
    draft_path = drafts[0]
    title = draft_path.stem.split("-", 2)[-1].rsplit("-v", 1)[0]
    publish(date_str, n, title, draft_path, allow_todo=allow_todo)
