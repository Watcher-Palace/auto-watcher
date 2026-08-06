'use strict';

// 发布热力图：每天发布了多少篇，渲染进「关于」页的版本信息节（`{% publish_heatmap %}`）。
//
// 数据源是流水线账本 `_pipeline/events.csv` 的 published 行——文章 frontmatter 的 `date`
// 是事件发生日、不是发布日，账本的「发布日期」列是发布日的唯一权威记录。
//
// 月份范围与脚注起始日都从数据算、不写死：账本里补进更早的发布日期（早期手写期文章目前
// 连行都没有），图会自动往前长。
//
// 与首页日历（scripts/calendar.js）画的不是一回事：那张按文章 `date` 画事件密度，这张按
// 发布日画本站的产出节奏，同一天的深浅只表示当天发了几篇。

const fs = require('fs');
const path = require('path');

const EMPTY_COLOR = '#ebedf0';

// 单色阶取站上「本站自身动作」的那支紫（M 标记、↺ 回顾同色系），避开绿色（首页日历的
// Day N 计数）与红橙黄（严重度阶梯），免得跨页面撞语义。
const BUCKETS = [
  { min: 10, color: '#6b5b95', label: '10+' },
  { min: 6, color: '#8c7fae', label: '6-9' },
  { min: 3, color: '#b3a9c8', label: '3-5' },
  { min: 1, color: '#d9d4e3', label: '1-2' },
];

function splitCsvLine(line) {
  const out = [];
  let cur = '';
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (quoted) {
      if (ch === '"') {
        if (line[i + 1] === '"') { cur += '"'; i++; } else { quoted = false; }
      } else {
        cur += ch;
      }
    } else if (ch === '"') {
      quoted = true;
    } else if (ch === ',') {
      out.push(cur);
      cur = '';
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out;
}

// 'YYMMDD' -> 当天发布篇数
function readPublishCounts(csvPath) {
  const lines = fs.readFileSync(csvPath, 'utf8').split(/\r?\n/).filter((l) => l.trim() !== '');
  if (!lines.length) return new Map();
  const header = splitCsvLine(lines[0]);
  const iState = header.indexOf('状态');
  const iPub = header.indexOf('发布日期');
  if (iState < 0 || iPub < 0) return new Map();

  const counts = new Map();
  for (const line of lines.slice(1)) {
    const f = splitCsvLine(line);
    if ((f[iState] || '').trim() !== 'published') continue;
    const d = (f[iPub] || '').trim();
    if (!/^\d{6}$/.test(d)) continue;
    counts.set(d, (counts.get(d) || 0) + 1);
  }
  return counts;
}

function colorFor(n) {
  for (const b of BUCKETS) if (n >= b.min) return b.color;
  return EMPTY_COLOR;
}

function ymOf(key) {
  return `20${key.slice(0, 2)}-${key.slice(2, 4)}`;
}

function daysInMonth(ym) {
  const [y, m] = ym.split('-').map(Number);
  return new Date(y, m, 0).getDate();
}

function monthRange(firstYm, lastYm) {
  const out = [];
  let [y, m] = firstYm.split('-').map(Number);
  const [ly, lm] = lastYm.split('-').map(Number);
  while (y < ly || (y === ly && m <= lm)) {
    out.push(`${y}-${String(m).padStart(2, '0')}`);
    m += 1;
    if (m > 12) { m = 1; y += 1; }
  }
  return out;
}

const STYLE = `<style>
.pubheat{margin:0 0 1.4em;font-size:12px;line-height:1}
.pubheat-grid{display:inline-block}
.pubheat-row{display:flex;align-items:center;margin-bottom:2px}
.pubheat-label{width:4.6em;flex:none;color:#666;font-size:11px}
.pubheat-cell{width:11px;height:11px;margin-right:2px;border-radius:2px;flex:none}
.pubheat-cell-void{background:transparent}
.pubheat-ruler .pubheat-tick{width:13px;flex:none;color:#999;font-size:10px;text-align:left}
.pubheat-legend{display:flex;align-items:center;margin-top:6px;color:#666;font-size:11px}
.pubheat-legend .pubheat-cell{margin-left:4px}
.pubheat-legend span.pubheat-legend-label{margin-left:3px}
.pubheat-note{margin-top:6px;color:#888;font-size:11px;line-height:1.6}
</style>`;

function render(counts) {
  if (!counts.size) return '';

  const keys = [...counts.keys()].sort();
  const firstYm = ymOf(keys[0]);
  const now = new Date();
  const nowYm = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`;
  const lastYm = ymOf(keys[keys.length - 1]);
  const months = monthRange(firstYm, lastYm > nowYm ? lastYm : nowYm);

  const parts = [STYLE, '<div class="pubheat"><div class="pubheat-grid">'];

  // 日期刻度（每 5 天一个）
  parts.push('<div class="pubheat-row pubheat-ruler"><span class="pubheat-label"></span>');
  for (let d = 1; d <= 31; d++) {
    parts.push(`<span class="pubheat-tick">${d === 1 || d % 5 === 0 ? d : ''}</span>`);
  }
  parts.push('</div>');

  for (const ym of months) {
    const len = daysInMonth(ym);
    parts.push(`<div class="pubheat-row"><span class="pubheat-label">${ym}</span>`);
    for (let d = 1; d <= 31; d++) {
      if (d > len) {
        parts.push('<span class="pubheat-cell pubheat-cell-void"></span>');
        continue;
      }
      const key = `${ym.slice(2, 4)}${ym.slice(5, 7)}${String(d).padStart(2, '0')}`;
      const n = counts.get(key) || 0;
      const date = `${ym}-${String(d).padStart(2, '0')}`;
      const title = n ? `${date} 发布 ${n} 篇` : `${date} 无发布`;
      parts.push(`<span class="pubheat-cell" style="background:${colorFor(n)}" title="${title}"></span>`);
    }
    parts.push('</div>');
  }
  parts.push('</div>');

  // 图例
  parts.push('<div class="pubheat-legend"><span>少</span>');
  parts.push(`<span class="pubheat-cell" style="background:${EMPTY_COLOR}" title="无发布"></span>`);
  for (const b of [...BUCKETS].reverse()) {
    parts.push(`<span class="pubheat-cell" style="background:${b.color}" title="${b.label} 篇"></span>`);
  }
  parts.push('<span class="pubheat-legend-label">多</span></div>');

  const total = [...counts.values()].reduce((a, b) => a + b, 0);
  const start = `20${keys[0].slice(0, 2)}-${keys[0].slice(2, 4)}-${keys[0].slice(4, 6)}`;
  parts.push(
    `<div class="pubheat-note">统计自 ${start}（账本记录的最早发布日）起：${keys.length} 个发布日，共 ${total} 篇。` +
    '深浅只表示当天发布的篇数，与事件严重度无关；批量补发的日子会明显偏深。' +
    '更早的文章尚未在账本中记录发布日期，暂不计入。</div>'
  );

  parts.push('</div>');
  return parts.join('');
}

hexo.extend.tag.register('publish_heatmap', function () {
  const csvPath = path.join(hexo.base_dir, '_pipeline', 'events.csv');
  try {
    return render(readPublishCounts(csvPath));
  } catch (e) {
    hexo.log.warn(`publish_heatmap: 读取 ${csvPath} 失败，跳过热力图 — ${e.message}`);
    return '';
  }
});
