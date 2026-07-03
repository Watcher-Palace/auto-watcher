# Daily tracker cron

One small incremental fetch per day (~4–8 requests for 4 UIDs) keeps the
pipeline current and stays far below Weibo's account-level throttle. Missed
days are harmless: `--daily` resumes from per-UID `last_seen_id` and any
saved budget/rate-limit cursor in `_pipeline/.tracker-state.json`.

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
