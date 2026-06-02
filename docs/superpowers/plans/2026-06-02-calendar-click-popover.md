# Calendar Click-to-Open Title Popover Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the calendar's native hover tooltip with a click-to-open popover: clicking an event segment shows a floating box with that event's title, and clicking the title navigates to the article.

**Architecture:** All changes live in the single Hexo build-time generator `scripts/calendar.js`. Each event segment is emitted as a focusable `<span class="cal-trigger">` carrying `data-title`/`data-url` (HTML-attribute-escaped) instead of an `<a ... title>`. A small vanilla-JS `<script>` (one delegated click/keydown listener) and matching CSS are concatenated into the page markdown exactly as the existing `<style>` block is. The script creates one reusable popover `<div>`, fills it with a real `<a href>` title link, positions it with `position:fixed` from the trigger's bounding rect, and handles toggle/outside-click/Esc dismissal.

**Tech Stack:** Hexo generator API (JS), `hexo-renderer-marked` (passes raw HTML/`<style>`/`<script>` through untouched), vanilla browser JS/CSS. No new dependencies.

**Verification note:** `scripts/calendar.js` is a build-time generator with no JS unit-test harness in this repo. Per the design spec, each task is verified by running `pnpm build` and grepping the generated `public/index.html` for the expected markers, plus a final manual click-test via `pnpm run server`. All commands run from the repo root `/home/jc/Projects/auto-watcher`.

---

### Task 1: Convert event segments from `<a>` links to `<span class="cal-trigger">`

**Files:**
- Modify: `scripts/calendar.js` (add `escapeAttr` helper near line 33; change the event-link `.map` at lines 72–77)

- [ ] **Step 1: Add the `escapeAttr` helper**

Insert this function declaration immediately **before** `function splitLabel(n) {` (currently line 33). Function declarations are hoisted, so placement within the generator scope is fine.

```javascript
  // HTML-attribute-escape a value (order matters: & first)
  function escapeAttr(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
```

- [ ] **Step 2: Replace the event-link map with span triggers**

In `cellContent`, replace this exact block (currently lines 72–77):

```javascript
      const links = posts.slice(0, 4).map((post, i) => {
        const color = CAT_COLOR[post.cat];
        const bold = CAT_BOLD.has(post.cat) ? 'font-weight:bold;' : '';
        const safeTitle = post.title.replace(/"/g, '&quot;');
        return `<a style="color:${color};${bold}" href="${post.urlPath}" title="${safeTitle}">${labels[i]}</a>`;
      });
```

with:

```javascript
      const links = posts.slice(0, 4).map((post, i) => {
        const color = CAT_COLOR[post.cat];
        const bold = CAT_BOLD.has(post.cat) ? 'font-weight:bold;' : '';
        const safeTitle = escapeAttr(post.title);
        const safeUrl = escapeAttr(post.urlPath);
        return `<span class="cal-trigger" role="button" tabindex="0" data-title="${safeTitle}" data-url="${safeUrl}" style="color:${color};${bold}">${labels[i]}</span>`;
      });
```

Leave the surrounding code (the `splitLabel`, the `sep` joining with the grey `_`, and the `return \`${day}<br>${links.join(sep)}\``) unchanged. The variable name `links` is kept as-is to minimize the diff.

- [ ] **Step 3: Build the site**

Run: `pnpm build`
Expected: completes without error; output includes a line like `INFO  Generated: index.html`.

- [ ] **Step 4: Verify the generated markup**

Run:
```bash
grep -c 'class="cal-trigger"' public/index.html
grep -c 'data-url=' public/index.html
grep -c '<a style="color:' public/index.html
grep -c '本月总结' public/index.html
grep -c 'Day ' public/index.html
```
Expected:
- `class="cal-trigger"` count ≥ 1 (event segments now render as spans)
- `data-url=` count ≥ 1
- `<a style="color:` count **= 0** (event links were the only inline-colored `<a>`; they are now spans — confirms the old tooltip links are gone)
- `本月总结` count ≥ 1 (May summary heading link still present — untouched)
- `Day ` count ≥ 1 (green gap counters still present — untouched)

- [ ] **Step 5: Commit**

```bash
git add scripts/calendar.js
git commit -m "feat(calendar): render event segments as click triggers (spans)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Add popover CSS and the click/keyboard behavior script

**Files:**
- Modify: `scripts/calendar.js` (extend the `<style>` block at lines 155–157; add a `script` const after the `css` const; append `${script}` to the `md` template)

- [ ] **Step 1: Add popover CSS to the existing `<style>` block**

Replace this exact block (currently lines 155–157):

```javascript
  .calendar-table a { text-decoration: none; }
  .month-summary { font-size: 0.6em; font-weight: normal; }
</style>`;
```

with:

```javascript
  .calendar-table a { text-decoration: none; }
  .month-summary { font-size: 0.6em; font-weight: normal; }
  .cal-trigger { cursor: pointer; }
  .cal-popover {
    position: fixed;
    display: none;
    background: #fff;
    border: 1px solid #ccc;
    border-radius: 4px;
    padding: 6px 10px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.2);
    z-index: 1000;
    max-width: 16em;
    font-size: 0.9rem;
  }
  .cal-popover.open { display: block; }
  .cal-popover-link { text-decoration: none; }
</style>`;
```

- [ ] **Step 2: Add the behavior script as a `const`**

Immediately **after** the `css` template-literal const ends (i.e., right after the line `</style>\`;` you just edited) and **before** the comment `// Render markdown intro + CSS + calendar HTML` (currently line 159), insert:

```javascript
  const script = `<script>
(function () {
  var openTrigger = null;
  var pop = document.createElement('div');
  pop.className = 'cal-popover';
  var link = document.createElement('a');
  link.className = 'cal-popover-link';
  pop.appendChild(link);
  document.body.appendChild(pop);

  function closePop() {
    pop.classList.remove('open');
    openTrigger = null;
  }

  function openPop(trigger) {
    link.textContent = trigger.getAttribute('data-title') || '';
    link.setAttribute('href', trigger.getAttribute('data-url') || '#');
    pop.classList.add('open');
    var rect = trigger.getBoundingClientRect();
    var left = rect.left;
    var maxLeft = window.innerWidth - pop.offsetWidth - 8;
    if (left > maxLeft) left = maxLeft;
    if (left < 8) left = 8;
    pop.style.top = (rect.bottom + 4) + 'px';
    pop.style.left = left + 'px';
    openTrigger = trigger;
  }

  document.addEventListener('click', function (e) {
    var trigger = e.target.closest ? e.target.closest('.cal-trigger') : null;
    if (trigger) {
      if (openTrigger === trigger) closePop(); else openPop(trigger);
      return;
    }
    if (!(e.target.closest && e.target.closest('.cal-popover'))) closePop();
  });

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closePop(); return; }
    var trigger = e.target.closest ? e.target.closest('.cal-trigger') : null;
    if (trigger && (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar')) {
      e.preventDefault();
      if (openTrigger === trigger) closePop(); else openPop(trigger);
    }
  });
})();
</script>`;
```

Notes for the implementer:
- This is a backtick template literal. It contains no `${` interpolation and no literal backtick or `</script>` sequence, so it is safe to embed verbatim.
- `pop.offsetWidth` is measured after `.open` is added (so `display:block` is in effect) — the value is valid.

- [ ] **Step 3: Append the script to the page markdown**

Replace this exact line (currently line 160):

```javascript
  const md = `骗你的，没有不愤怒的义务（动感夹心，2026）。\n\n${css}\n${calendarHtml}`;
```

with:

```javascript
  const md = `骗你的，没有不愤怒的义务（动感夹心，2026）。\n\n${css}\n${calendarHtml}\n${script}`;
```

- [ ] **Step 4: Build the site**

Run: `pnpm build`
Expected: completes without error; output includes `INFO  Generated: index.html`.

- [ ] **Step 5: Verify CSS and script landed un-escaped**

Run:
```bash
grep -c 'cal-popover' public/index.html
grep -c 'document.addEventListener' public/index.html
grep -c '&lt;script&gt;' public/index.html
```
Expected:
- `cal-popover` count ≥ 1 (the CSS rules are present)
- `document.addEventListener` count ≥ 1 (the script body is present and **not** HTML-escaped — `hexo-renderer-marked` passed it through like the `<style>` block)
- `&lt;script&gt;` count **= 0** (the script tag was not escaped)

- [ ] **Step 6: Manual click-test**

Run: `pnpm run server` then open http://localhost:4000/auto-watcher/ and verify:
- Clicking an event segment (e.g. a colored `挑`/`战`) opens a small floating box below it showing that event's title.
- Clicking the title in the box navigates to that article.
- Clicking the same segment again closes the box; clicking a different segment switches; clicking empty space closes it; pressing `Esc` closes it.
- A multi-event day (e.g. 2026-05-04, which has the orange AI-篡改 case) shows one box per segment with the correct per-segment title.
- Tab to a segment and press Enter — the box opens (keyboard access).
- The green `Day N` counters and the `本月总结` heading link still look and behave as before.

Stop the server (`Ctrl-C`) when done.

- [ ] **Step 7: Commit**

```bash
git add scripts/calendar.js
git commit -m "feat(calendar): click-to-open title popover with keyboard + dismissal

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Interaction model (one popover per event segment, span trigger, title as `<a href>`) → Task 1 Step 2 + Task 2 Step 2. ✓
- First click opens (no direct navigation) → trigger is a `<span>`, not `<a>` (Task 1). ✓
- One popover at a time; toggle / switch / outside-click / Esc → Task 2 Step 2 click + keydown handlers. ✓
- Keyboard accessible (`tabindex`/`role`, Enter/Space) → Task 1 markup + Task 2 keydown handler. ✓
- Full HTML-attribute escaping of title and URL → `escapeAttr` (Task 1 Step 1–2). ✓
- Fixed positioning from rect, viewport-edge clamp → Task 2 `openPop`. ✓
- CSS (`.cal-trigger`, `.cal-popover`, `.open`, `.cal-popover-link`) → Task 2 Step 1. ✓
- Unchanged: colors, `挑战失败` split, `_` separators, 4-event cap, `Day N`, `本月总结` → not modified; verified by greps (Task 1 Step 4, Task 2 Step 5). ✓
- Verification by build + grep + manual click-test → every task. ✓

**Placeholder scan:** No TBD/TODO/vague steps; every code step shows complete code. ✓

**Type/name consistency:** `cal-trigger`, `cal-popover`, `cal-popover-link`, `data-title`, `data-url`, `escapeAttr`, `openPop`, `closePop`, `openTrigger` used identically across CSS, markup, and script. ✓
