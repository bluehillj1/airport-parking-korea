'use strict';

const AIRPORTS = [['GMP', '김포'], ['PUS', '김해'], ['CJU', '제주']];
const STALE_MINUTES = 15;
const REFRESH_MS = 120000;

let latest = null;
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

function renderLots() {
  const main = document.getElementById('lots');
  main.textContent = '';
  const airport = latest && latest.airports && latest.airports[current];
  const p = document.createElement('p');
  p.className = 'empty';
  p.textContent = airport && airport.lots ? `${airport.lots.length}곳 수신` : '데이터 없음';
  main.appendChild(p);
}

async function init() {
  renderTabs();
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
