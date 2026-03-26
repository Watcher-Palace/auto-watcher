import re
from src.utils import pipeline
from src.utils.web import WebClient

REVIEWER_SYSTEM = """You are an independent fact-checker and editor for a Chinese feminist news blog.
You have NOT seen the researcher's notes. Review the draft independently.

Check:
1. Factual accuracy — verify key claims against public sources (search if needed)
2. Neutrality — flag loaded language or one-sided framing
3. Format — verify it follows the blog template (概述, 信息来源, correct front matter)
4. Sources — are claims cited? Are any sources missing?

For each issue, insert an inline comment in the draft where it appears:
<!-- [REVIEWER]: your note here -->

If you cannot independently verify a claim (e.g. paywalled source), add:
<!-- [REVIEWER]: [UNVERIFIED — source may be valid but not independently confirmed] -->

End your output with a ## Review Summary section listing key issues."""


def run_reviewer(date_str: str, index: int, claude, web) -> None:
    """Review the latest draft for an event independently."""
    draft_info = pipeline.latest_draft(date_str, index)
    if not draft_info:
        raise FileNotFoundError(f"No draft found for {date_str}-{index}")

    draft_path, draft_v = draft_info
    draft_content = draft_path.read_text()

    urls = re.findall(r'https?://\S+', draft_content)
    verification_content = []
    for url in urls[:5]:
        try:
            html = web.fetch(url)
            text = web.extract_text(html)
            verification_content.append(f"[{url}]\n{text[:2000]}")
        except WebClient.FetchError:
            verification_content.append(f"[{url}] (无法访问，标记为UNVERIFIED)")

    sources_text = "\n\n---\n\n".join(verification_content)
    user_prompt = (
        f"博客草稿：\n\n{draft_content}\n\n"
        f"独立核实的来源内容：\n\n{sources_text}"
    )

    review = claude.simple(REVIEWER_SYSTEM, user_prompt)

    review_path, _ = pipeline.next_review_path(date_str, index)
    review_path.write_text(review)
