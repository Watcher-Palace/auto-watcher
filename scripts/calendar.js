'use strict';

hexo.extend.generator.register('calendar-index', function (locals) {
  const moment = require('moment');

  const CAT_COLOR = { S: 'darkred', A: 'red', B: 'orange', C: 'yellow', D: '#777', N: '#777' };
  const CAT_BOLD = new Set(['S']);
  const FAIL_CATS = new Set(['S', 'A', 'B', 'C', 'D']);        // 显示"挑战失败"
  const ELLIPSIS_CATS = new Set(['N']);                        // 显示"……"
  const RENDER_CATS = new Set(['S', 'A', 'B', 'C', 'D', 'N']); // 走"挑战失败"/省略号通道；均重置绿色计数
  const CAT_PRIORITY = { S: 0, A: 1, B: 2, C: 3, D: 4, N: 5 };
  const RETRO_COLOR = '#6b5b95';                               // 那年今日回顾：↺ 按档位取色，无档位时回退这个紫
  const PROGRESS_COLOR = '#6b5b95';                            // 正向进展（M）：紫色加粗 M
  const root = hexo.config.root || '/';

  // Build date map: 'YYMMDD' -> [{ cat, urlPath, title }, ...] sorted by priority
  // 那年今日回顾（frontmatter `retrospect`）走 retroMap、正向进展（categories: M）走
  // progressMap，两者都不进 dateMap：前者重访的是往年的失败、后者根本不是失败，所以都
  // 不显示"挑战失败"、也不重置绿色 Day N 计数，只在日期号旁挂一个可点的标记。
  const dateMap = {};
  const retroMap = {};
  const progressMap = {};

  // ↺ 落在「原事件的月日 ＋ 本站收录年份」那一格。年份取源文件名（`YYMMDD[-N].md` 即收录
  // 日期）而不是 `date`：`date` 是最新事实进展发生日，回填旧案时它可能落在 2023 这种日历
  // 根本不渲染的年份（日历只从 2026-01 起，见下方 start），↺ 就会落进不存在的月历里。收录
  // 年份＝本站在哪一年做的这次回顾，正是 ↺ 该出现的年份。2-29 撞非闰年时收到当月最后一天。
  function retroYear(post) {
    const m = /^(\d{2})\d{4}(?:-\d+)?$/.exec(post.slug || '');
    return m ? 2000 + Number(m[1]) : post.date.year();
  }

  function retroKey(post) {
    let retro = moment(String(post.retrospect), 'YYYY-MM-DD', true);
    if (!retro.isValid()) retro = moment(post.retrospect);      // YAML 已解析成 Date 的情形
    if (!retro.isValid()) return post.date.format('YYMMDD');
    const base = moment({ year: retroYear(post), month: retro.month(), day: 1 });
    return base.date(Math.min(retro.date(), base.daysInMonth())).format('YYMMDD');
  }

  locals.posts.each(post => {
    const key = post.date.format('YYMMDD');
    const urlPath = root + post.path.replace(/\/index\.html$/, '/');
    if (post.retrospect) {
      const rkey = retroKey(post);
      if (!retroMap[rkey]) retroMap[rkey] = [];
      retroMap[rkey].push({ urlPath, title: post.title, cat: (post.categories.first() || {}).name });
      return;
    }
    const cat = (post.categories.first() || { name: 'N' }).name;
    if (cat === 'M') {
      if (!progressMap[key]) progressMap[key] = [];
      progressMap[key].push({ urlPath, title: post.title });
      return;
    }
    if (!RENDER_CATS.has(cat)) return;
    if (!dateMap[key]) dateMap[key] = [];
    dateMap[key].push({ cat, urlPath, title: post.title });
  });
  Object.values(dateMap).forEach(posts =>
    posts.sort((a, b) => CAT_PRIORITY[a.cat] - CAT_PRIORITY[b.cat])
  );

  // Build summary-page map: 'YYMM' -> url, from pages carrying a summary_month marker
  const summaryMap = {};
  locals.pages.each(page => {
    if (!page.summary_month) return;
    summaryMap[String(page.summary_month)] = root + page.path.replace(/\/index\.html$/, '/');
  });

  // HTML-attribute-escape a value (order matters: & first)
  function escapeAttr(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // Split '挑战失败' into n parts (max 4), distributing chars front-heavy
  function splitLabel(n) {
    const chars = ['挑', '战', '失', '败'];
    n = Math.min(n, 4);
    if (n === 1) return ['挑战失败'];
    const parts = [];
    let rem = 4;
    for (let i = 0; i < n; i++) {
      const size = Math.ceil(rem / (n - i));
      parts.push(chars.splice(0, size).join(''));
      rem -= size;
    }
    return parts;
  }

  // One clickable calendar entry (popover shows the post title, links to the post)
  function trigger(post, text, color, bold) {
    const safeTitle = escapeAttr(post.title);
    const safeUrl = escapeAttr(post.urlPath);
    return `<span class="cal-trigger" role="button" tabindex="0" data-title="${safeTitle}" data-url="${safeUrl}" style="color:${color};${bold || ''}">${text}</span>`;
  }

  // Day number, followed by a ↺ per 那年今日回顾 post and a bold M per 正向进展 post —
  // same line as the number so a real event on that day still gets the second line to itself.
  function dayHead(day, key) {
    const marks = (retroMap[key] || [])
      .map(p => trigger(p, '↺', CAT_COLOR[p.cat] || RETRO_COLOR, CAT_BOLD.has(p.cat) ? 'font-weight:bold;' : ''))
      .concat((progressMap[key] || []).map(p => trigger(p, 'M', PROGRESS_COLOR, 'font-weight:bold;')));
    if (marks.length === 0) return String(day);
    return `${day} ${marks.join(' ')}`;
  }

  // Sorted list of boundary event dates (S/A/B/C/D/N) — each resets the green counter
  const boundaryDates = Object.keys(dateMap)
    .map(k => moment('20' + k, 'YYYYMMDD'))
    .sort((a, b) => a.valueOf() - b.valueOf());

  function lastBoundaryBefore(m) {
    let last = null;
    for (const d of boundaryDates) {
      if (d.isSameOrBefore(m, 'day')) last = d;
      else break;
    }
    return last;
  }

  function cellContent(year, month, day) {
    const date = moment({ year, month: month - 1, day });
    const today = moment().startOf('day');
    if (date.isAfter(today, 'day')) return String(day);

    const key = date.format('YYMMDD');
    const head = dayHead(day, key);
    const posts = dateMap[key];

    if (posts) {
      const failPosts = posts.filter(p => FAIL_CATS.has(p.cat));
      const nPosts = posts.filter(p => ELLIPSIS_CATS.has(p.cat));
      const labels = splitLabel(failPosts.length);
      const catTrigger = (post, text) =>
        trigger(post, text, CAT_COLOR[post.cat], CAT_BOLD.has(post.cat) ? 'font-weight:bold;' : '');
      const segs = failPosts.slice(0, 4).map((post, i) => catTrigger(post, labels[i]));
      nPosts.forEach(post => segs.push(catTrigger(post, '……')));
      const sep = '<span style="color:#999;">-</span>';
      return `${head}<br>${segs.join(sep)}`;
    }

    // Untracked gap: leave blank
    const gapStart = moment('2026-01-28');
    const gapEnd = moment('2026-03-20');
    if (date.isBetween(gapStart, gapEnd, 'day', '[]')) return head;

    const lastBoundary = lastBoundaryBefore(date);
    if (lastBoundary) {
      const dayN = date.diff(lastBoundary, 'days');
      return `${head}<br><span style="color:green;">Day ${dayN}</span>`;
    }

    return head;
  }

  function monthTable(m) {
    const year = m.year();
    const month = m.month() + 1;
    const daysInMonth = m.daysInMonth();
    const firstDow = m.clone().startOf('month').day(); // 0=Sun

    const yymm = m.format('YYMM');
    const summaryUrl = summaryMap[yymm];
    const heading = summaryUrl
      ? `## ${year}年${month}月 <a class="month-summary" href="${summaryUrl}">本月总结</a>`
      : `## ${year}年${month}月（待维护）`;

    let rows = '';
    let cells = Array(firstDow).fill('<td></td>');

    for (let d = 1; d <= daysInMonth; d++) {
      cells.push(`<td>${cellContent(year, month, d)}</td>`);
      if (cells.length === 7) {
        rows += `    <tr>${cells.join('')}</tr>\n`;
        cells = [];
      }
    }
    if (cells.length > 0) {
      while (cells.length < 7) cells.push('<td></td>');
      rows += `    <tr>${cells.join('')}</tr>\n`;
    }

    return `\n${heading}\n
<table class="calendar-table">
  <thead><tr><th>日</th><th>一</th><th>二</th><th>三</th><th>四</th><th>五</th><th>六</th></tr></thead>
  <tbody>
${rows}  </tbody>
</table>`;
  }

  const today = moment();
  const start = moment('2026-01-01');
  const months = [];
  for (let m = start.clone(); m.isSameOrBefore(today, 'month'); m.add(1, 'month')) {
    months.push(m.clone());
  }

  const calendarHtml = months.map(m => monthTable(m)).join('\n');

  const css = `<style>
  .calendar-table {
    width: 100%;
    table-layout: fixed;
    border-collapse: collapse;
    background-color: #e0e0e0;
    margin: 1em 0;
  }
  .calendar-table th,
  .calendar-table td {
    border: 1px solid #ddd;
    text-align: center;
    padding: 4px 6px;
  }
  .calendar-table th { background-color: #f2f2f2; font-weight: bold; }
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

  // IMPORTANT: this <script> must contain NO blank lines. The calendar table + this
  // script render as one contiguous raw-HTML block that hexo-renderer-marked passes
  // through verbatim — but a single blank line ENDS that block, and everything after it
  // gets re-parsed as markdown (smartypants turns ' into ‘’ and = into &#x3D;, and wraps
  // lines in <p>/<br>), producing invalid JS that silently throws on load. Keep every
  // line non-empty. Same reason the <style> block above has no blank lines.
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

  // Render markdown intro + CSS + calendar HTML
  const md = `骗你的，没有不愤怒的义务（动感夹心，2026）。\n\n${css}\n${calendarHtml}\n${script}`;

  return hexo.render.render({ text: md, engine: 'markdown' }).then(renderedContent => {
    return {
      path: 'index.html',
      layout: ['page'],
      data: {
        title: '挑战当女的不被惹怒！',
        date: moment('2026-01-26'),
        content: renderedContent,
        path: '',
        permalink: root
      }
    };
  });
});
