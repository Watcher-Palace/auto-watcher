# Daily tracker cron

One incremental fetch per day keeps the pipeline current while staying far
below Weibo's account-level throttle. Page count scales with posting volume:
quiet accounts cost 1–2 pages/day, a prolific one (dozens of posts/day) may
need 5–10; the run is capped at `--budget` page fetches (default 40 ≈ ~400
posts across all UIDs) with jittered 3–9s delays — a normal-browsing
signature, not the 80-requests-in-minutes backfill burst that trips the
throttle. Missed days and budget overflows are harmless: `--daily` resumes
from per-UID `last_seen_id` and any saved cursor in
`_pipeline/.tracker-state.json`, and UIDs with a pending cursor are fetched
first on the next run. If your accounts are heavy posters, raise the cap,
e.g. `--daily --budget 60`.

## Install (WSL, cron is already running on this machine)

```bash
(crontab -l 2>/dev/null; echo '15 9 * * * cd /home/jc/Projects/auto-watcher && src/venv/bin/python src/tracker.py --daily >> _pipeline/tracker.log 2>&1') | crontab -
```

- `15 9 * * *` = 09:15 local time daily; adjust freely. Runs only fetch +
  Haiku filter (writes `_pipeline/events/`); research → publish stays manual.
- Log: `_pipeline/tracker.log` (append-only; a few lines/day).
- Exit 2 in the log means rate-limited — the cursor is saved and the next
  run resumes automatically; no action needed.

## Caveats

- WSL cron only fires while the WSL VM is up. If the machine/VM is off at
  09:15, that day is skipped — harmless, the next run covers the gap.
- If cron ever stops: `sudo service cron start` (or
  `sudo systemctl enable --now cron` with systemd).

## Alternative: Windows Task Scheduler (fires even when WSL is idle)

Program: `wsl.exe`
Arguments:

```
-d Ubuntu -- bash -lc 'cd /home/jc/Projects/auto-watcher && src/venv/bin/python src/tracker.py --daily >> _pipeline/tracker.log 2>&1'
```

Trigger: daily 09:15, "Run task as soon as possible after a scheduled start
is missed" enabled. (Replace `Ubuntu` with your distro name from `wsl -l`.)
