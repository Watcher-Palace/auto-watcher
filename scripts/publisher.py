import calendar as cal
import re
import shutil
import subprocess
from datetime import date, datetime
from pathlib import Path

from scripts.utils import pipeline

CONFLICT_SENTINEL = "<!-- CONFLICT-UNRESOLVED"
BLOG_ROOT = Path(__file__).parent.parent.parent
POSTS_DIR = BLOG_ROOT / "source" / "_posts"
INDEX_MD = BLOG_ROOT / "source" / "index.md"

MONTH_NAMES_ZH = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二"]


def has_conflict_sentinel(content: str) -> bool:
    return CONFLICT_SENTINEL in content


def determine_published_filename(date_str: str, posts_dir: Path = POSTS_DIR) -> str:
    """Return the next available filename for a given date (YYMMDD.md, YYMMDD-2.md, ...)."""
    if not (posts_dir / f"{date_str}.md").exists():
        return f"{date_str}.md"
    n = 2
    while (posts_dir / f"{date_str}-{n}.md").exists():
        n += 1
    return f"{date_str}-{n}.md"


def run_publisher(date_str: str, index: int) -> str:
    """
    Publish the latest approved draft. Returns the published filename.
    Raises ValueError if draft contains conflict sentinel.
    """
    draft_info = pipeline.latest_draft(date_str, index)
    if not draft_info:
        raise FileNotFoundError(f"No draft found for {date_str}-{index}")

    draft_path, _ = draft_info
    draft_content = draft_path.read_text()

    if has_conflict_sentinel(draft_content):
        raise ValueError(
            f"Draft for {date_str}-{index} contains unresolved conflicts. "
            "Resolve <!-- CONFLICT-UNRESOLVED --> blocks before publishing."
        )

    filename = determine_published_filename(date_str)
    slug = filename.replace(".md", "")
    dest = POSTS_DIR / filename

    shutil.copy2(draft_path, dest)

    if "{% asset_path" in draft_content:
        asset_dir = POSTS_DIR / slug
        asset_dir.mkdir(exist_ok=True)

    title, post_date = _extract_frontmatter(draft_content, date_str)

    inject_calendar_entry(INDEX_MD, post_date, slug, title)

    subprocess.run(["pnpm", "run", "build"], cwd=BLOG_ROOT, check=True)
    subprocess.run(["pnpm", "run", "deploy"], cwd=BLOG_ROOT, check=True)

    return filename


def _extract_frontmatter(content: str, date_str: str) -> tuple[str, date]:
    """Extract title and date from YAML front matter."""
    title_m = re.search(r'^title:\s*(.+)$', content, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else f"事件{date_str}"

    date_m = re.search(r'^date:\s*(\d{4}-\d{2}-\d{2})', content, re.MULTILINE)
    if date_m:
        post_date = datetime.strptime(date_m.group(1), "%Y-%m-%d").date()
    else:
        post_date = datetime.strptime("20" + date_str, "%Y%m%d").date()

    return title, post_date


def inject_calendar_entry(
    index_file: Path,
    post_date: date,
    slug: str,
    title: str,
) -> None:
    """Inject a calendar <a> entry into source/index.md for the given date."""
    content = index_file.read_text()
    month_header = f"## {post_date.year}年{MONTH_NAMES_ZH[post_date.month - 1]}月"

    if month_header not in content:
        content = _append_new_month(content, post_date)

    content = _inject_link(content, post_date, slug, title)
    index_file.write_text(content)


def _inject_link(content: str, post_date: date, slug: str, title: str) -> str:
    """Find the correct <td> for the day and inject the link."""
    month_header = f"## {post_date.year}年{MONTH_NAMES_ZH[post_date.month - 1]}月"
    month_start = content.index(month_header)

    next_section = re.search(r'\n## ', content[month_start + len(month_header):])
    month_end = (
        month_start + len(month_header) + next_section.start()
        if next_section
        else len(content)
    )

    month_content = content[month_start:month_end]
    day = post_date.day
    year = post_date.year

    link = (
        f'\n        <a style="color: grey;"\n'
        f'           href="{{{{ site.root }}}}{year}/{slug}/"\n'
        f'           title="{title}">待标注</a>'
    )

    # Case 1: empty cell <td>DAY</td>
    empty = re.compile(rf'<td>{day}</td>')
    if empty.search(month_content):
        new_month = empty.sub(f'<td>{day}<br>{link}\n      </td>', month_content, count=1)
        return content[:month_start] + new_month + content[month_end:]

    # Case 2: cell with existing link(s) — append before </td>
    existing = re.compile(rf'(<td>{day}<br>(?:(?!</td>).)*?)(</td>)', re.DOTALL)
    new_month = existing.sub(
        lambda m: m.group(1) + link + '\n      ' + m.group(2),
        month_content,
        count=1,
    )
    return content[:month_start] + new_month + content[month_end:]


def _append_new_month(content: str, post_date: date) -> str:
    """Generate and append a new month calendar section."""
    month_name = MONTH_NAMES_ZH[post_date.month - 1]
    header = f"## {post_date.year}年{month_name}月"

    month_cal = cal.monthcalendar(post_date.year, post_date.month)
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
        "  <thead>\n"
        "    <tr>\n"
        "      <th>日</th><th>一</th><th>二</th><th>三</th>"
        "<th>四</th><th>五</th><th>六</th>\n"
        "    </tr>\n"
        "  </thead>\n"
        "  <tbody>\n"
        + "\n".join(rows) + "\n"
        "  </tbody>\n"
        "</table>\n"
    )
    return content.rstrip() + table
