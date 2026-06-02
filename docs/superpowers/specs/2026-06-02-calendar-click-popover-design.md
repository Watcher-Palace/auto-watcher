# Calendar Click-to-Open Title Popover — Design

**Date:** 2026-06-02
**Status:** Approved
**Scope:** `scripts/calendar.js` only (Hexo build-time generator for `/index.html`).

## Goal

Replace the calendar's current hover tooltip with a click-to-open popover. Clicking
an event segment opens a small floating box showing that event's title; clicking the
title navigates to the article.

## Current Behavior (what we're changing)

On an event day, `cellContent` renders the split label `挑战失败` as one color-coded
`<a>` per event:

```html
<a style="color:orange;" href="/auto-watcher/260504/" title="女学生生活照遭AI篡改…">挑</a>
```

The "floating window on hover" is the **native browser tooltip** produced by the
`title="..."` attribute. Clicking the link navigates directly to the article.

We are removing that tooltip and the direct-navigation-on-first-click behavior.

## New Behavior

### Interaction model — one popover per event segment

- Each event maps to one clickable **trigger**: the same color-coded segment shown
  today (`挑`/`战`/… on multi-event days, or the whole `挑战失败` on single-event days).
- The trigger is no longer an `<a>`. The **first click opens a popover** instead of
  navigating.
- The popover is a small floating box anchored just below the clicked trigger. It
  contains the event title rendered as a real `<a href>` link to the article.
- Clicking the title link navigates to the article (standard link; crawlable).
- **One popover open at a time:**
  - Clicking the same trigger again closes it (toggle).
  - Clicking a different trigger closes the current one and opens the new one.
  - Clicking anywhere outside an open popover/trigger closes it.
  - Pressing `Esc` closes it.
- **Keyboard accessible:** triggers are focusable (`tabindex="0"`, `role="button"`)
  and open the popover on `Enter` / `Space`. The title link inside is natively
  focusable.

### Unchanged

- The green `Day N` gap counter cells.
- The `本月总结` month-heading summary links.
- Category → color mapping (`S` darkred bold, `A` red, `B` orange, `C` yellow), the
  grey `_` separators, the front-heavy `挑战失败` split, the 4-event cap, and category
  ordering by priority.
- Which posts appear on the calendar (only categories S/A/B/C, via `dateMap`).

## Implementation — Approach #1 (vanilla JS)

Chosen over the native Popover API (immature cross-browser anchor positioning; needs
unique IDs per popover) and a CSS-only approach (fragile positioning, weak dismissal
and accessibility).

### Trigger markup

In `cellContent`, each event segment becomes a `<span>` carrying the title and URL as
data attributes, styled exactly as the current link:

```html
<span class="cal-trigger" role="button" tabindex="0"
      data-title="女学生生活照遭AI篡改…" data-url="/auto-watcher/260504/"
      style="color:orange;">挑</span>
```

- `data-title` and the visible color carry the same information the old `title`
  attribute and link color did.
- Both `data-title` and `data-url` values are HTML-attribute-escaped (`&` `<` `>` `"`).
  The existing code already escapes `"`; extend to the full set so titles with `&`/`<`
  render safely.
- The grey `_` separators between segments are unchanged.

### Popover element

A single reusable `<div class="cal-popover">` is created once by the script and
appended to `<body>`. On open it is filled with one anchor:

```html
<a class="cal-popover-link" href="DATA_URL">DATA_TITLE</a>
```

(The script sets `.textContent` / `.href` from the trigger's dataset, so no escaping
concerns at runtime.)

### Positioning

`position: fixed`, placed from the trigger's `getBoundingClientRect()` (left aligned to
the trigger, top just below it). Fixed positioning avoids clipping by the calendar
table's cell borders/overflow. If the box would overflow the right edge of the viewport,
shift it left to stay on-screen.

### Script

One `<script>` block appended to the page content (after the calendar HTML), using a
delegated click listener on `document`:

- Click on a `.cal-trigger` → if that trigger's popover is already open, close; else open
  (fill, position, show) for that trigger.
- Click elsewhere (not inside `.cal-popover`) → close.
- `keydown` `Escape` → close.
- `keydown` `Enter`/`Space` on a focused `.cal-trigger` → open (prevent default scroll
  for Space).

State: a module-scoped variable holding the currently-open trigger element (or `null`).

### CSS

Add to the existing `<style>` block:

- `.cal-trigger { cursor: pointer; }` (color/bold still set inline per category).
- `.cal-popover { position: fixed; display: none; background: #fff; border: 1px solid
  #ccc; border-radius: 4px; padding: 6px 10px; box-shadow: 0 2px 6px rgba(0,0,0,0.2);
  z-index: 1000; max-width: 16em; font-size: 0.9rem; }`
- `.cal-popover.open { display: block; }`
- `.cal-popover-link { text-decoration: none; }`

## Data Flow

Build time (`hexo generate`): `dateMap` already holds `{ cat, urlPath, title }` per
event. `cellContent` emits `<span class="cal-trigger" data-title data-url style>` per
event instead of `<a href title>`. The CSS and the new `<script>` are concatenated into
the page markdown alongside the existing CSS, exactly as CSS is today.

Runtime (browser): delegated listeners drive open/close/navigate. No data fetching.

## Edge Cases

- **Single-event day:** one trigger spanning the whole `挑战失败`; same mechanism.
- **>4 events:** unchanged — only the first 4 (by priority) render, so at most 4
  triggers, matching today's behavior.
- **Title with quotes/ampersands/angle brackets:** escaped in the `data-*` attributes;
  rendered via `textContent` at runtime.
- **Popover near viewport right edge:** shifted left to remain visible.
- **No JavaScript:** the title is not reachable (the trigger is a `<span>`, not a
  link). Acceptable for this internal landing page; noted as a known limitation.

## Testing / Verification

`scripts/calendar.js` is a build-time generator with no JS unit-test harness in this
repo (tests are Python/pytest for the tracker/publisher). Verify by:

1. `pnpm build` succeeds.
2. Inspect generated `public/index.html`: event days contain
   `<span class="cal-trigger" ... data-title=... data-url=...>` (no `<a ... title=...>`
   inside event cells), the `.cal-popover` CSS is present, and the `<script>` is
   present. `Day N` counters and `本月总结` links unchanged.
3. `pnpm run server` and manually click-test: click a segment opens the box, title
   click navigates, second click / outside click / Esc closes, switching between
   segments works, keyboard (Tab to a trigger, Enter to open) works.

## Out of Scope

- No change to which events appear, colors, the `挑战失败` split, or summary links.
- No new build dependencies.
- No hover tooltip retained (click-only, per request).
