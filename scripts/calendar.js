'use strict';

hexo.extend.generator.register('calendar-index', function (locals) {
  const moment = require('moment');

  const CAT_COLOR = { S: 'darkred', A: 'red', B: 'orange', C: 'yellow' };
  const CAT_BOLD = new Set(['S']);
  const AC_CATS = new Set(['S', 'A', 'B', 'C']);
  const CAT_PRIORITY = { S: 0, A: 1, B: 2, C: 3, D: 4, N: 5 };
  const root = hexo.config.root || '/';

  // Build date map: 'YYMMDD' -> [{ cat, urlPath, title }, ...] sorted by priority
  const dateMap = {};
  locals.posts.each(post => {
    const cat = (post.categories.first() || { name: 'N' }).name;
    if (!AC_CATS.has(cat)) return;
    const key = post.date.format('YYMMDD');
    const urlPath = root + post.path.replace(/\/index\.html$/, '/');
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

  // Sorted list of A-C event dates (moment objects)
  const acDates = Object.keys(dateMap)
    .map(k => moment('20' + k, 'YYYYMMDD'))
    .sort((a, b) => a.valueOf() - b.valueOf());

  function lastACBefore(m) {
    let last = null;
    for (const d of acDates) {
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
    const posts = dateMap[key];

    if (posts) {
      const labels = splitLabel(posts.length);
      const links = posts.slice(0, 4).map((post, i) => {
        const color = CAT_COLOR[post.cat];
        const bold = CAT_BOLD.has(post.cat) ? 'font-weight:bold;' : '';
        const safeTitle = escapeAttr(post.title);
        const safeUrl = escapeAttr(post.urlPath);
        return `<span class="cal-trigger" role="button" tabindex="0" data-title="${safeTitle}" data-url="${safeUrl}" style="color:${color};${bold}">${labels[i]}</span>`;
      });
      const sep = '<span style="color:#999;">_</span>';
      return `${day}<br>${links.join(sep)}`;
    }

    // Untracked gap: leave blank
    const gapStart = moment('2026-01-28');
    const gapEnd = moment('2026-03-20');
    if (date.isBetween(gapStart, gapEnd, 'day', '[]')) return String(day);

    const lastAC = lastACBefore(date);
    if (lastAC) {
      const dayN = date.diff(lastAC, 'days');
      return `${day}<br><span style="color:green;">Day ${dayN}</span>`;
    }

    return String(day);
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
      : `## ${year}年${month}月`;

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
</style>`;

  // Render markdown intro + CSS + calendar HTML
  const md = `骗你的，没有不愤怒的义务（动感夹心，2026）。\n\n${css}\n${calendarHtml}`;

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
