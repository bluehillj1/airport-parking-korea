'use strict';

const AIRPORTS = [['GMP', '김포'], ['PUS', '김해'], ['CJU', '제주']];
const STALE_MINUTES = 15;
const REFRESH_MS = 120000;
const SPARK = '▁▂▃▄▅▆▇█';

let latest = null;
let todayCache = {};
// Guards against overlapping renders (tab tap during the 2-minute refresh, or a
// slow today-*.json fetch). Without it both runs clear, await, then append -> dupes.
let renderToken = 0;
let current = localStorage.getItem('airport') || 'GMP';
if (!AIRPORTS.some(([code]) => code === current)) current = 'GMP';

async function loadJson(path) {
  const res = await fetch(`${path}?t=${Date.now()}`, { cache: 'no-store' });
  if (!res.ok) throw new Error(`${path} ${res.status}`);
  return res.json();
}

// source_ts is KST wall-clock text with no offset. Pin it to +09:00 explicitly so
// the elapsed time is identical no matter what timezone the phone is set to.
function minutesSince(sourceTs) {
  if (!sourceTs) return null;
  const t = Date.parse(sourceTs.replace(' ', 'T') + '+09:00');
  if (Number.isNaN(t)) return null;
  return Math.floor((Date.now() - t) / 60000);
}

function renderFreshness() {
  const el = document.getElementById('freshness');
  const mins = latest ? minutesSince(latest.source_ts) : null;
  if (mins === null) {
    el.textContent = '정보를 불러오지 못했습니다';
    el.classList.add('stale');
    return;
  }
  let text = mins <= 1 ? '방금 전 정보' : `${mins}분 전 정보`;
  const stale = mins >= STALE_MINUTES;
  if (stale) text += ' — 갱신이 멈췄을 수 있습니다';
  el.textContent = text;
  el.classList.toggle('stale', stale);
}

function renderTabs() {
  const nav = document.getElementById('airports');
  nav.textContent = '';
  for (const [code, label] of AIRPORTS) {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.textContent = label;
    btn.setAttribute('aria-pressed', String(code === current));
    btn.addEventListener('click', () => {
      if (current === code) return;
      current = code;
      localStorage.setItem('airport', code);
      renderTabs();
      renderLots();
    });
    nav.appendChild(btn);
  }
}

function isKnown(lot) {
  return lot && lot.free !== null && lot.free !== undefined;
}

// A 15-car swing on a 1763-space lot is noise, not a trend. Force the chart to span
// at least 5% of capacity so small wobbles stay visually flat instead of inventing drama.
function sparkline(values, total) {
  const pts = (values || []).filter(v => v !== null && v !== undefined && !Number.isNaN(v));
  if (pts.length < 2) return '';
  const tail = pts.slice(-24);
  let lo = Math.min(...tail);
  let hi = Math.max(...tail);
  const floor = Math.max(2, (total || 0) * 0.05);
  if (hi - lo < floor) {
    const mid = (hi + lo) / 2;
    lo = mid - floor / 2;
    hi = mid + floor / 2;
  }
  const span = hi - lo;
  return tail.map(v => {
    const r = (v - lo) / span;
    const i = Math.min(SPARK.length - 1, Math.max(0, Math.round(r * (SPARK.length - 1))));
    return SPARK[i];
  }).join('');
}

function accessLabel(lot, shuttle) {
  const a = (lot && lot.access) || {};
  if (a.requires_shuttle) {
    const hw = shuttle && shuttle.headway_min;
    if (Array.isArray(hw) && hw.length === 2 && hw[0] !== null && hw[1] !== null) {
      return hw[0] === hw[1] ? `셔틀 ${hw[0]}분 간격` : `셔틀 ${hw[0]}~${hw[1]}분 간격`;
    }
    return '셔틀 이용';
  }
  const w = a.walk_min;
  if (Array.isArray(w) && w.length === 2 && w[0] !== null && w[1] !== null) {
    return w[0] === w[1] ? `도보 ${w[0]}분` : `도보 ${w[0]}~${w[1]}분`;
  }
  // confidence "unverified" -> we do not know the real walking time, so don't claim one.
  return '도보권';
}

function trendLabel(lot) {
  if (!isKnown(lot)) return '정보를 받지 못했습니다';
  // The source counter freezes at 100%, so a full lot's delta is meaningless.
  if (lot.grade === '만차') return '만차 — 입출차 정보 없음';
  const t = lot.trend;
  if (!t) return '추세 집계 중';
  if (!t.significant) return '→ 큰 변화 없음';
  return t.delta > 0
    ? `↗ ${t.span_minutes}분 +${t.delta}대`
    : `↘ ${t.span_minutes}분 ${t.delta}대`;
}

// Rule 2: 정보 없음 last, 만차 before that, then walk-accessible before shuttle-only,
// then most free spaces first. Unknown lots are ranked explicitly so `null - null`
// (NaN) never reaches the comparator and silently corrupts the sort.
function lotRank(lot) {
  if (!isKnown(lot) || lot.grade === '정보 없음') return 3;
  if (lot.grade === '만차') return 2;
  return lot.access && lot.access.requires_shuttle ? 1 : 0;
}

function sortLots(lots) {
  return (lots || []).slice().sort((a, b) => {
    const ra = lotRank(a);
    const rb = lotRank(b);
    if (ra !== rb) return ra - rb;
    const fa = isKnown(a) ? a.free : -1;
    const fb = isKnown(b) ? b.free : -1;
    if (fa !== fb) return fb - fa;
    return String(a && a.name || '').localeCompare(String(b && b.name || ''), 'ko');
  });
}

function lotCard(lot, shuttle, curve) {
  const card = document.createElement('section');
  card.className = 'lot';

  const head = document.createElement('div');
  head.className = 'lot-head';
  const name = document.createElement('span');
  name.className = 'lot-name';
  name.textContent = lot.name === null || lot.name === undefined ? '이름 없음' : lot.name;
  const grade = document.createElement('span');
  grade.className = 'grade';
  const g = lot.grade || '정보 없음';
  grade.classList.add(g);
  grade.textContent = g;
  head.appendChild(name);
  head.appendChild(grade);
  card.appendChild(head);

  // Free SPACES are the headline: 99% and 91% look alike but mean 17 vs 151 cars.
  const free = document.createElement('p');
  free.className = 'free';
  const pct = document.createElement('small');
  if (isKnown(lot)) {
    free.textContent = `${lot.free}면`;
    if (lot.total) pct.textContent = `${Math.round((lot.occupied / lot.total) * 100)}% 사용`;
  } else {
    free.textContent = '—';
    pct.textContent = '실시간 정보 없음';
  }
  free.appendChild(pct);
  card.appendChild(free);

  const meta = document.createElement('p');
  meta.className = 'meta';
  meta.textContent = accessLabel(lot, shuttle);
  card.appendChild(meta);

  const spark = curve ? sparkline(curve.occupied, curve.total !== null && curve.total !== undefined ? curve.total : lot.total) : '';
  const trend = document.createElement('p');
  trend.className = 'meta';
  if (spark && lot.grade !== '만차') {
    const s = document.createElement('span');
    s.className = 'spark';
    s.textContent = spark;
    trend.appendChild(s);
    trend.appendChild(document.createTextNode(' '));
  }
  trend.appendChild(document.createTextNode(trendLabel(lot)));
  card.appendChild(trend);

  return card;
}

async function renderLots() {
  const token = ++renderToken;
  const main = document.getElementById('lots');
  const airport = latest && latest.airports && latest.airports[current];
  if (!airport || !Array.isArray(airport.lots) || airport.lots.length === 0) {
    main.textContent = '';
    const p = document.createElement('p');
    p.className = 'empty';
    p.textContent = '데이터 없음';
    main.appendChild(p);
    return;
  }

  const code = current;
  if (!todayCache[code]) {
    try {
      todayCache[code] = await loadJson(`data/today-${code}.json`);
    } catch (err) {
      // Degraded API: no curves today. Cards must still render — this is exactly
      // the moment the page matters most.
      console.error(`today-${code}.json 로드 실패`, err);
      todayCache[code] = { lots: {} };
    }
  }
  // A newer render started while we awaited; that one owns the DOM now.
  if (token !== renderToken) return;
  main.textContent = '';
  const today = todayCache[code] || { lots: {} };
  const curves = today.lots || {};
  const shuttle = airport.shuttle || null;

  const order = [];
  const groups = new Map();
  for (const lot of airport.lots) {
    const key = lot.terminal || '기타';
    if (!groups.has(key)) { groups.set(key, []); order.push(key); }
    groups.get(key).push(lot);
  }

  // 김포 has two terminals ~1km apart linked by a shuttle; 김해·제주 have one, so no headers.
  const multi = order.length > 1;
  for (const key of order) {
    if (multi) {
      const h = document.createElement('h2');
      h.className = 'terminal';
      h.textContent = key !== '국내선' && shuttle && shuttle.name
        ? `${key} — ${shuttle.name}`
        : key;
      main.appendChild(h);
    }
    for (const lot of sortLots(groups.get(key))) {
      main.appendChild(lotCard(lot, shuttle, curves[lot.name]));
    }
  }
}

async function init() {
  renderTabs();
  todayCache = {}; // drop cached curves so the 2-minute refresh picks up new points
  try {
    latest = await loadJson('data/latest.json');
  } catch (err) {
    console.error('latest.json 로드 실패', err);
  }
  renderFreshness();
  renderLots();
}

init();
setInterval(init, REFRESH_MS);
