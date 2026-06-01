# Auto Watcher Palace

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
- **CI**: GitHub Actions runs the test suite on every push/PR (`.github/workflows/tests.yml`)

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
WEIBO_COOKIE=...               # required for tracker
TRACKED_UIDS=uid1,uid2,uid3    # Weibo UIDs the tracker fetches
```

Set in `src/.env`. LLM filtering runs through the local `claude` CLI (Claude Code subscription) — there is no external API key.

### Getting a Weibo Cookie

The cookie must come from the **mobile** Weibo domain (`m.weibo.cn`), not `weibo.com`. The desktop `SUB`/`SUBP` are domain-scoped and won't work.

1. Open https://m.weibo.cn in a desktop browser and log in
2. Open DevTools (`F12`) → **Application** tab → **Storage → Cookies → https://m.weibo.cn**
3. Copy the values for these 5 fields:
   - `_T_WM`
   - `ALF`
   - `SSOloginstate`
   - `SUB`
   - `SUBP`
4. Format as one line in `src/.env`:
   ```
   WEIBO_COOKIE=_T_WM=xxx; ALF=xxx; SSOloginstate=xxx; SUB=xxx; SUBP=xxx
   ```

**Faster alternative:** in DevTools' **Network** tab, reload the page, click any `m.weibo.cn` request, and copy the entire `Cookie:` request header value.

Cookies expire — if the tracker logs `failed to fetch uid ...` for every UID, the cookie needs refreshing.
