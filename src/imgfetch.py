"""证据图/文书下载器：带 Referer 抓取并校验类型与大小，防占位图。"""
from __future__ import annotations
import sys
import urllib.request
from pathlib import Path

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
MAGIC = {b"\xff\xd8\xff": "jpg", b"\x89PNG": "png", b"GIF8": "gif",
         b"RIFF": "webp", b"%PDF": "pdf"}
MIN_BYTES = 2048


def classify(data: bytes) -> str:
    kind = next((k for m, k in MAGIC.items() if data.startswith(m)), None)
    if kind is None:
        raise ValueError(f"不是图片/PDF（前 16 字节：{data[:16]!r}）——可能拿到防盗链占位页")
    if len(data) < MIN_BYTES:
        raise ValueError(f"文件过小（{len(data)}B < {MIN_BYTES}B）——疑似占位图")
    return kind


def fetch(url: str, dest: Path, referer: str | None = None) -> str:
    headers = {"User-Agent": UA}
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    data = urllib.request.urlopen(req, timeout=30).read()
    kind = classify(data)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return f"OK {dest}（{len(data)}B {kind}）"


if __name__ == "__main__":
    argv = sys.argv[1:]
    if len(argv) < 2:
        raise SystemExit("usage: python src/imgfetch.py <url> <dest> [--referer URL]")
    ref = argv[argv.index("--referer") + 1] if "--referer" in argv else None
    try:
        print(fetch(argv[0], Path(argv[1]), ref))
    except Exception as e:
        raise SystemExit(f"FAIL {argv[0]}: {e}")
