'use strict';

const AIRPORTS = [['GMP', '김포'], ['PUS', '김해'], ['CJU', '제주']];
const STALE_MINUTES = 5;
const REFRESH_MS = 60000;
const HISTORY_MAX = 60;
const SPARK = '▁▂▃▄▅▆▇█';

let data = null;
let timer = null;
// 서버에 저장소가 없으므로 추세는 이 페이지가 열려 있는 동안만 쌓인다.
// key: `${공항코드}|${주차장명}` -> [{t: epochMs, v: 주차대수}]
const lotHistory = {};
let current = localStorage.getItem('airport') || 'GMP';
if (!AIRPORTS.some(([code]) => code === current)) current = 'GMP';

// source_ts는 오프셋 없는 KST 벽시계 문자열이다. +09:00을 명시해 고정하지 않으면
// 휴대폰 시간대 설정에 따라 경과 시간이 달라진다.
function sourceEpoch(sourceTs) {
  if (!sourceTs) return null;
  const t = Date.parse(String(sourceTs).replace(' ', 'T') + '+09:00');
  return Number.isNaN(t) ? null : t;
}

function minutesSince(sourceTs) {
  const t = sourceEpoch(sourceTs);
  return t === null ? null : Math.floor((Date.now() - t) / 60000);
}

function show(id, visible) {
  document.getElementById(id).hidden = !visible;
}

// ---------------------------------------------------------------- 로그인

function showLogin(message) {
  if (timer !== null) { clearInterval(timer); timer = null; }
  show('app', false);
  show('login', true);
  // 폼은 /api/parking 응답을 받은 뒤에야 나타난다. 로드 직후에만 비우면 그
  // 청소가 지나간 다음에 자동완성이 채워 넣는다. 보이는 순간에 다시 비운다.
  clearPassword();
  setTimeout(() => { if (!userTypedPassword) clearPassword(); }, 300);
  document.getElementById('login-msg').textContent = message || '';
  passwordInput.focus();
}

// 비밀번호 칸은 무엇이 들어 있는지 아무도 볼 수 없다. 한/영 상태가 잘못됐든
// 브라우저가 옛 값을 채웠든 점 개수만 보이니, 원인을 찾을 길이 없이 '암호가
// 틀렸다'만 반복된다. 보이게 하고, 세고, 비운다.
const passwordInput = document.getElementById('password');
const passwordCount = document.getElementById('pw-count');
let userTypedPassword = false;

function updatePasswordCount() {
  passwordCount.textContent = `${passwordInput.value.length}자`;
}

function clearPassword() {
  passwordInput.value = '';
  userTypedPassword = false;
  updatePasswordCount();
}

passwordInput.addEventListener('input', () => {
  userTypedPassword = true;
  updatePasswordCount();
});

document.getElementById('reveal').addEventListener('change', (event) => {
  passwordInput.type = event.target.checked ? 'text' : 'password';
});

// 자동완성은 로드가 끝난 뒤에 일어나기도 한다. 사용자가 이미 치기 시작했다면
// 건드리지 않는다.
clearPassword();
setTimeout(() => { if (!userTypedPassword) clearPassword(); }, 400);

// 전부 "암호가 틀렸다"로 뭉뚱그리면 설정 실수를 영원히 못 찾는다. 틀린 암호와
// 설정 누락과 미배포는 대응이 서로 다르므로 구분해서 말한다.
// 사용자 입력에 대해서만 모호하게 답하면 된다 — 서버는 여전히 401에 이유를 싣지 않는다.
function loginError(status, sentLength) {
  // 보낸 길이를 함께 보여준다. 친 글자 수와 다르면 입력칸에 내가 치지 않은 값이
  // 섞여 있다는 뜻이고, 그건 화면에서 즉시 알아야 할 사실이다.
  if (status === 401) return `암호가 맞지 않습니다. (보낸 길이 ${sentLength}자)`;
  if (status === 500) return '서버 환경변수가 설정되지 않았습니다. (Vercel 설정 확인)';
  if (status === 404) return 'API가 배포되지 않았습니다. (함수 빌드 확인)';
  if (status === 405) return '요청 방식 오류입니다.';
  return `로그인에 실패했습니다. (오류 ${status})`;
}

document.getElementById('login').addEventListener('submit', async (event) => {
  event.preventDefault();
  const msg = document.getElementById('login-msg');
  const sent = passwordInput.value;
  msg.textContent = '확인 중…';
  try {
    const res = await fetch('/api/login', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ password: sent }),
    });
    // 암호는 어디에도 남기지 않는다. 세션은 서버가 준 HttpOnly 쿠키에만 있다.
    clearPassword();
    if (!res.ok) {
      msg.textContent = loginError(res.status, sent.length);
      return;
    }
    msg.textContent = '';
    show('login', false);
    show('app', true);
    start();
  } catch (err) {
    msg.textContent = '연결에 실패했습니다.';
  }
});

// ---------------------------------------------------------------- 데이터

// 500은 환경변수 누락일 수도, lot_access.json 이 번들에 없을 수도 있다. 하나로
// 단정하면 엉뚱한 곳을 뒤지게 되므로 원인을 적어둔 곳을 가리킨다.
function dataError(status) {
  if (status === 500) return '서버 설정 오류입니다 (Vercel 로그 확인)';
  if (status === 502) return '공항 API가 응답하지 않습니다';
  if (status === 404) return 'API가 배포되지 않았습니다';
  return `실시간 정보를 가져오지 못했습니다 (오류 ${status})`;
}

async function loadData() {
  const res = await fetch('/api/parking', { cache: 'no-store' });
  if (res.status === 401) return { unauthorized: true };
  if (!res.ok) return { failed: dataError(res.status) };
  return { body: await res.json() };
}

// 같은 원천 타임스탬프가 다시 와도 점을 늘리지 않는다. 15초 캐시 때문에 같은
// 값이 반복해서 오는데, 그걸 쌓으면 없는 변화가 그래프에 그려진다.
function recordHistory(body) {
  const t = sourceEpoch(body && body.source_ts);
  if (t === null) return;
  for (const [code, airport] of Object.entries(body.airports || {})) {
    for (const lot of airport.lots || []) {
      if (!isKnown(lot)) continue;
      const key = `${code}|${lot.name}`;
      const points = lotHistory[key] || (lotHistory[key] = []);
      const last = points[points.length - 1];
      if (last && last.t === t) continue;
      points.push({ t, v: lot.occupied });
      if (points.length > HISTORY_MAX) points.shift();
    }
  }
}

function computeTrend(points, total) {
  if (!points || points.length < 2) return null;
  const first = points[0];
  const last = points[points.length - 1];
  const delta = last.v - first.v;
  return {
    delta,
    span: Math.max(1, Math.round((last.t - first.t) / 60000)),
    // 규모 대비 1% 미만(최소 3대)은 방향을 단정하지 않는다.
    significant: Math.abs(delta) >= Math.max(3, (total || 0) * 0.01),
  };
}

// ---------------------------------------------------------------- 렌더링

function renderFreshness(error) {
  const el = document.getElementById('freshness');
  if (error) {
    el.textContent = error;
    el.classList.add('stale');
    return;
  }
  const mins = data ? minutesSince(data.source_ts) : null;
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

// 1763면 주차장에서 15대 출렁임은 추세가 아니라 잡음이다. 최소 진폭을 정원의
// 5%로 강제해 작은 흔들림이 화면을 가득 채우지 않게 한다.
function sparkline(points, total) {
  if (!points || points.length < 2) return '';
  const tail = points.slice(-24).map(p => p.v);
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
  // confidence "unverified" — 실제 도보시간을 모르므로 분을 지어내지 않는다.
  return '도보권';
}

function trendLabel(lot, points) {
  if (!isKnown(lot)) return '정보를 받지 못했습니다';
  // 원천 카운터가 100%에서 고정되므로 만차 주차장의 증감은 의미가 없다.
  if (lot.grade === '만차') return '만차 — 입출차 정보 없음';
  const t = computeTrend(points, lot.total);
  if (!t) return '잠시 열어두면 변화가 보입니다';
  if (!t.significant) return '→ 큰 변화 없음';
  return t.delta > 0
    ? `↗ ${t.span}분 +${t.delta}대`
    : `↘ ${t.span}분 ${t.delta}대`;
}

// 정보 없음이 맨 뒤, 그 앞이 만차, 그다음 셔틀 전용, 도보권이 우선. 같은 등급
// 안에서는 빈자리가 많은 순. 미상 주차장은 순위를 명시해 null 연산이 NaN으로
// 새어들어 정렬을 조용히 망가뜨리는 일을 막는다.
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
    return String((a && a.name) || '').localeCompare(String((b && b.name) || ''), 'ko');
  });
}

function lotCard(lot, shuttle, points) {
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

  // 퍼센트가 아니라 빈 면수가 헤드라인이다. 99%와 91%는 비슷해 보이지만
  // 17면과 151면이다.
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

  const trend = document.createElement('p');
  trend.className = 'meta';
  const spark = lot.grade === '만차' ? '' : sparkline(points, lot.total);
  if (spark) {
    const s = document.createElement('span');
    s.className = 'spark';
    s.textContent = spark;
    trend.appendChild(s);
    trend.appendChild(document.createTextNode(' '));
  }
  trend.appendChild(document.createTextNode(trendLabel(lot, points)));
  card.appendChild(trend);

  return card;
}

function renderLots() {
  const main = document.getElementById('lots');
  main.textContent = '';
  const airport = data && data.airports && data.airports[current];
  if (!airport || !Array.isArray(airport.lots) || airport.lots.length === 0) {
    const p = document.createElement('p');
    p.className = 'empty';
    p.textContent = '데이터 없음';
    main.appendChild(p);
    return;
  }

  const shuttle = airport.shuttle || null;
  const order = [];
  const groups = new Map();
  for (const lot of airport.lots) {
    const key = lot.terminal || '기타';
    if (!groups.has(key)) { groups.set(key, []); order.push(key); }
    groups.get(key).push(lot);
  }

  // 김포는 국내선·국제선이 1km쯤 떨어져 셔틀로 이어진다. 김해·제주는 하나뿐이라
  // 구분 제목을 붙이지 않는다.
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
      main.appendChild(lotCard(lot, shuttle, lotHistory[`${current}|${lot.name}`]));
    }
  }
}

// ---------------------------------------------------------------- 순환

async function refresh() {
  let result;
  try {
    result = await loadData();
  } catch (err) {
    console.error('주차정보 요청 실패', err);
    renderFreshness('실시간 정보를 가져오지 못했습니다');
    return;
  }
  if (result.unauthorized) {
    showLogin('다시 로그인해 주세요.');
    return;
  }
  if (result.failed) {
    renderFreshness(result.failed);
    return;
  }
  data = result.body;
  recordHistory(data);
  renderFreshness();
  renderLots();
}

function start() {
  renderTabs();
  refresh();
  if (timer === null) timer = setInterval(refresh, REFRESH_MS);
}

// 첫 요청의 역할은 데이터를 받는 것이면서 동시에 인증 여부를 확인하는 것이다.
// 401이면 로그인 화면으로, 아니면 그대로 순환을 시작한다.
async function init() {
  let result;
  try {
    result = await loadData();
  } catch (err) {
    // 일시적 장애일 수 있으므로 화면은 띄우고 타이머로 회복을 기다린다.
    console.error('주차정보 요청 실패', err);
    show('app', true);
    renderTabs();
    renderFreshness('실시간 정보를 가져오지 못했습니다');
    if (timer === null) timer = setInterval(refresh, REFRESH_MS);
    return;
  }
  if (result.unauthorized) {
    showLogin('');
    return;
  }
  show('app', true);
  if (result.failed) {
    renderTabs();
    renderFreshness(result.failed);
    if (timer === null) timer = setInterval(refresh, REFRESH_MS);
    return;
  }
  data = result.body;
  recordHistory(data);
  renderTabs();
  renderFreshness();
  renderLots();
  if (timer === null) timer = setInterval(refresh, REFRESH_MS);
}

init();
