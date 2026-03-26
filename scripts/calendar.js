'use strict';

hexo.extend.generator.register('calendar-index', function (locals) {
  const moment = require('moment');

  const CAT_COLOR = { A: 'red', B: 'yellow', C: 'orange' };
  const AC_CATS = new Set(['A', 'B', 'C']);
  const CAT_PRIORITY = { A: 1, B: 2, C: 3, D: 4, N: 5 };
  const root = hexo.config.root || '/';

  // Build date map: 'YYMMDD' -> { cat, urlPath, title }
  const dateMap = {};
  locals.posts.each(post => {
    const cat = (post.categories.first() || { name: 'N' }).name;
    if (!AC_CATS.has(cat)) return; // only track A-C for calendar display
    const key = post.date.format('YYMMDD');
    if (!dateMap[key] || CAT_PRIORITY[cat] < CAT_PRIORITY[dateMap[key].cat]) {
      const urlPath = root + post.path.replace(/\/index\.html$/, '/');
      dateMap[key] = { cat, urlPath, title: post.title };
    }
  });

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
    const post = dateMap[key];

    if (post) {
      const color = CAT_COLOR[post.cat];
      const safeTitle = post.title.replace(/"/g, '&quot;');
      return `${day}<br><a style="color:${color};" href="${post.urlPath}" title="${safeTitle}">挑战失败</a>`;
    }

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

    return `\n## ${year}年${month}月\n
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
