"""月度总结发布：cp → pnpm build → pnpm run deploy（对齐 publisher 的链式顺序）。"""
from __future__ import annotations
import subprocess
import sys
from src.utils import pipeline as pl


def publish_summary(yymm: str, deploy: bool = True) -> None:
    src = pl.PIPELINE / "summary" / f"{yymm}.md"
    if not src.exists():
        raise SystemExit(f"找不到总结草稿：{src}")
    text = src.read_text(encoding="utf-8")
    if f'summary_month: "{yymm}"' not in text:
        raise SystemExit(f"frontmatter summary_month 与参数 {yymm} 不符")
    dst = pl.REPO_ROOT / "source" / "summaries" / f"{yymm}.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    print(f"已复制 → {dst}")
    if deploy:
        subprocess.run(["pnpm", "run", "build"], cwd=pl.REPO_ROOT, check=True)
        subprocess.run(["pnpm", "run", "deploy"], cwd=pl.REPO_ROOT, check=True)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: python src/publish_summary.py <YYMM>")
    publish_summary(sys.argv[1])
