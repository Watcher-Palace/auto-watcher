from __future__ import annotations
import shutil
import subprocess
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.utils.pipeline import REPO_ROOT, PIPELINE
from src.utils import ledger
from src.utils.archive import finalize_event


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


def move_assets(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def publish(date_str: str, n: int, title: str, draft_path: Path, deploy: bool = True) -> None:
    content = draft_path.read_text(encoding="utf-8")
    fm = read_frontmatter(content)
    validate_tags(fm.get("tags"), load_tag_registry())
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
    move_assets(assets_src, posts_dir / post_slug)
    if (posts_dir / post_slug).exists():
        print(f"Moved assets → {posts_dir / post_slug}")

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
    date_str = _sys.argv[1]
    n = int(_sys.argv[2])
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
    publish(date_str, n, title, draft_path)
