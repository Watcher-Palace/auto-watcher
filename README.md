# Auto Watcher Palace — 自动哨

A feminist news blog documenting women's rights events in China. Live at [watcher-palace.github.io/auto-watcher](https://watcher-palace.github.io/auto-watcher/).

## How It Works

Events are collected automatically from Weibo, researched, drafted, and reviewed by AI agents (Claude Code), then published after human approval.

```
Track (Weibo) → Research → Write → Review → [human gate] → Publish
```

## Event Categories

| Category | Description |
|----------|-------------|
| S | Government/national policy |
| A | Criminal cases; severely harmful events |
| B | Civil cases; significant events |
| C | Non-official organizations; minor events |
| D | Individual conduct |
| N | Neutral / awaiting follow-up |

## Stack

- **Blog**: Hexo + landscape theme, deployed to GitHub Pages (`gh-pages` branch)
- **Pipeline**: Python scripts in `src/`, AI agents in `.claude/skills/`
- **Tracking**: Weibo API via `src/tracker.py`

## Commands

```bash
pnpm run server                     # local preview at localhost:4000
pnpm run build && pnpm run deploy   # build and push to GitHub Pages
git push                            # push source changes
```

```bash
source src/venv/bin/activate
python src/tracker.py YYMMDD          # track events for a date
python src/publisher.py YYMMDD N      # publish approved draft
pytest src/tests/                     # run tests
```

## Environment Variables

```
WEIBO_COOKIE=...        # required for tracker
OPENROUTER_API_KEY=...  # required for tracker (LLM filtering)
```

Set in `src/.env`.
