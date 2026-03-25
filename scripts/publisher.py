from __future__ import annotations
import calendar as cal
import re
import shutil
import subprocess
import sys
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.utils.pipeline import REPO_ROOT, PIPELINE

CATEGORY_COLORS = {"A": "red", "B": "yellow", "C": "orange", "D": "orange", "N": "black"}
MONTH_NAMES_ZH = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]


def read_frontmatter(content: str) -> dict:
    if not content.startswith("---"):
        return {}
    end = content.index("---", 3)
    return yaml.safe_load(content[3:end]) or {}


def calendar_color(category: str) -> str:
    return CATEGORY_COLORS.get(category, "black")


def copy_draft(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def move_assets(src: Path, dst: Path) -> None:
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


def inject_calendar_entry(
    index_path: Path, date_str: str, title: str, category: str, post_slug: str
) -> None:
    year = "20" + date_str[:2]
    month = int(date_str[2:4])
    day = int(date_str[4:6])
    color = calendar_color(category)
    link = (
        f'\n        <a style="color: {color};"'
        f'\n           href="{{{{ site.root }}}}{year}/{post_slug}/"'
        f'\n           title="{title}">{title[:6]}</a>'
    )

    content = index_path.read_text(encoding="utf-8")
    month_header = f"## {year}年{MONTH_NAMES_ZH[month - 1]}月"
    if month_header not in content:
        content = _append_new_month(content, int(year), month)

    # Case 1: empty cell <td>DAY</td>
    empty = re.compile(rf'<td>{day}</td>')
    if empty.search(content):
        new_content = empty.sub(f'<td>{day}<br>{link}\n      </td>', content, count=1)
    else:
        # Case 2: cell with existing link(s) — append before </td>
        existing = re.compile(rf'(<td>{day}<br>(?:(?!</td>).)*?)(</td>)', re.DOTALL)
        new_content = existing.sub(
            lambda m: m.group(1) + link + '\n      ' + m.group(2),
            content,
            count=1,
        )

    index_path.write_text(new_content, encoding="utf-8")


def _append_new_month(content: str, year: int, month: int) -> str:
    month_name = MONTH_NAMES_ZH[month - 1]
    header = f"## {year}年{month_name}月"
    month_cal = cal.monthcalendar(year, month)
    rotated = [[week[6]] + week[:6] for week in month_cal]
    rows = []
    for week in rotated:
        cells = "\n".join(
            f"      <td>{day if day else ''}</td>" for day in week
        )
        rows.append(f"    <tr>\n{cells}\n    </tr>")
    table = (
        f"\n\n{header}\n\n"
        "<table class=\"calendar-table\">\n"
        "  <thead>\n    <tr>\n"
        "      <th>日</th><th>一</th><th>二</th><th>三</th>"
        "<th>四</th><th>五</th><th>六</th>\n"
        "    </tr>\n  </thead>\n  <tbody>\n"
        + "\n".join(rows) + "\n"
        "  </tbody>\n</table>\n"
    )
    return content.rstrip() + table


def publish(date_str: str, n: int, title: str, draft_path: Path, deploy: bool = True) -> None:
    fm = read_frontmatter(draft_path.read_text(encoding="utf-8"))
    posts_dir = REPO_ROOT / "source" / "_posts"
    post_slug = date_str

    copy_draft(draft_path, posts_dir / f"{date_str}.md")
    print(f"Copied draft → {posts_dir / f'{date_str}.md'}")

    assets_src = PIPELINE / "draft" / f"{date_str}-{n}-assets"
    move_assets(assets_src, posts_dir / date_str)
    if (posts_dir / date_str).exists():
        print(f"Moved assets → {posts_dir / date_str}")

    inject_calendar_entry(
        index_path=REPO_ROOT / "source" / "index.md",
        date_str=date_str,
        title=fm.get("title", title),
        category=str(fm.get("categories", "N")),
        post_slug=post_slug,
    )
    print("Updated index.md calendar")

    if deploy:
        subprocess.run(["pnpm", "run", "deploy"], cwd=REPO_ROOT, check=True)
        print("Deployed to GitHub Pages")


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
