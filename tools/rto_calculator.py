"""Driver working and rest time planner (Mintrans order No. 160 of 14.04.2026).

The page plans a trip: given the total driving time (or distance and average
speed) and the departure time, it lays out driving blocks of up to 4 h 30 min,
45-minute breaks, daily rest and, on long trips, weekly rest, and shows the
arrival time. The planning logic is plain JS (PLANNER_JS) so it can be tested
with node as well as run in the browser.

Limits used (order No. 160, in force 01.09.2026 – 01.09.2032):
- driving: 9 h per day, up to 10 h not more than twice a week;
  56 h per calendar week, 90 h per two consecutive weeks;
- break: at least 45 min after at most 4 h 30 min of driving;
- daily rest: at least 11 h, reducible to 9 h not more than 3 times between
  weekly rests;
- weekly rest: at least 45 h, before the start of the 7th working day.
"""
from __future__ import annotations

import html
import json

PAGE_PATH = "/tools/rezhim-truda-i-otdyha/"
ORDER_URL = "https://www.consultant.ru/document/cons_doc_LAW_534382/"

LIMITS = {
    "block": 270,        # max continuous driving, minutes
    "break": 45,         # break after a block
    "day": 540,          # daily driving
    "day_ext": 600,      # extended daily driving (<= 2 times a week)
    "ext_per_week": 2,
    "rest": 660,         # daily rest
    "rest_reduced": 540, # reduced daily rest (<= 3 times between weekly rests)
    "reduced_per_week": 3,
    "week": 3360,        # 56 h driving per week
    "two_weeks": 5400,   # 90 h per two weeks
    "weekly_rest": 2700, # 45 h
    "days_before_weekly": 6,
}

PLANNER_JS = r"""
function planTrip(opts, L) {
  // opts: {driveMin, startMs, extDays, reducedRest}
  let remaining = Math.max(0, Math.round(opts.driveMin));
  let t = opts.startMs;
  const M = 60000;
  const events = [];
  let weekDrive = 0, prevWeekDrive = 0, daysInWeek = 0, extUsed = 0, redUsed = 0;
  let dayNo = 0, weeklyRests = 0, extTotal = 0, redTotal = 0;
  const extAllowed = Math.max(0, Math.min(L.ext_per_week, opts.extDays | 0));
  let guard = 0;
  while (remaining > 0 && guard++ < 500) {
    const weekCap = Math.min(L.week - weekDrive, L.two_weeks - prevWeekDrive - weekDrive);
    if (weekCap <= 0 || daysInWeek >= L.days_before_weekly) {
      events.push({type: 'weekly', start: t, end: t + L.weekly_rest * M, min: L.weekly_rest});
      t += L.weekly_rest * M; weeklyRests++;
      prevWeekDrive = weekDrive; weekDrive = 0; daysInWeek = 0; extUsed = 0; redUsed = 0;
      continue;
    }
    let limit = L.day;
    let dayDrive = Math.min(remaining, limit, weekCap);
    if (remaining > L.day && extUsed < extAllowed && weekCap > L.day) {
      limit = L.day_ext; dayDrive = Math.min(remaining, limit, weekCap); extUsed++; extTotal++;
    }
    dayNo++;
    const day = {type: 'day', no: dayNo, start: t, drive: dayDrive, breaks: 0, segments: [], extended: limit === L.day_ext};
    let left = dayDrive;
    while (left > 0) {
      const chunk = Math.min(L.block, left);
      day.segments.push({kind: 'drive', start: t, end: t + chunk * M, min: chunk});
      t += chunk * M; left -= chunk;
      if (left > 0) {
        day.segments.push({kind: 'break', start: t, end: t + L.break * M, min: L.break});
        t += L.break * M; day.breaks++;
      }
    }
    day.end = t;
    events.push(day);
    remaining -= dayDrive; weekDrive += dayDrive; daysInWeek++;
    if (remaining <= 0) break;
    const nextCap = Math.min(L.week - weekDrive, L.two_weeks - prevWeekDrive - weekDrive);
    if (daysInWeek >= L.days_before_weekly || nextCap <= 0) continue; // weekly rest at loop top
    let rest = L.rest, reduced = false;
    if (opts.reducedRest && redUsed < L.reduced_per_week) { rest = L.rest_reduced; reduced = true; redUsed++; redTotal++; }
    events.push({type: 'rest', start: t, end: t + rest * M, min: rest, reduced: reduced});
    t += rest * M;
  }
  return {events: events, arrival: t, days: dayNo, weeklyRests: weeklyRests, extDays: extTotal, reducedRests: redTotal,
          totalMin: Math.round((t - opts.startMs) / M)};
}
if (typeof module !== 'undefined') module.exports = {planTrip: planTrip};
"""

FAQ = [
    (
        "Сколько часов водитель грузовика может быть за рулём в сутки?",
        "По приказу Минтранса № 160 — не более 9 часов. Увеличить до 10 часов можно не чаще двух раз в неделю. "
        "За календарную неделю — не более 56 часов, за любые две недели подряд — не более 90 часов.",
    ),
    (
        "Когда водитель обязан сделать перерыв?",
        "Не позднее чем через 4 часа 30 минут управления — специальный перерыв не менее 45 минут. "
        "Его можно разделить на две части: первая не менее 15 минут, последняя не менее 30 минут.",
    ),
    (
        "Какой должен быть ежедневный отдых?",
        "Не менее 11 часов, и он должен закончиться в течение 24 часов с начала работы. "
        "Сократить его до 9 часов можно не более трёх раз между двумя еженедельными отдыхами.",
    ),
    (
        "Какой должен быть еженедельный отдых?",
        "Не менее 45 часов подряд, до начала седьмого рабочего дня после предыдущего еженедельного отдыха. "
        "Сократить до 24 часов можно не чаще раза в две недели с последующей компенсацией.",
    ),
    (
        "Действует ли приказ № 424?",
        "Нет. С 1 сентября 2026 года приказ № 424 утратил силу, режим труда и отдыха водителей определяет приказ Минтранса № 160 от 14.04.2026. "
        "На водителей международных перевозок распространяются правила ЕСТР.",
    ),
]


def _page_css() -> str:
    return """
.calc-card{margin-top:14px;padding:26px;border:1px solid var(--line);border-radius:16px;background:var(--paper)}
.calc-card h2{margin:6px 0 14px;font-size:26px;line-height:1.1;letter-spacing:-.03em}
.calc-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-top:12px}
.calc-row[hidden]{display:none}
.calc-field{display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--muted);min-width:0}
.calc-field select,.calc-field input{font:inherit;font-size:15px;color:var(--ink);padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:#fff;min-width:0;width:100%;box-sizing:border-box}
.calc-check{display:flex;gap:10px;align-items:flex-start;font-size:14px;color:var(--ink);margin-top:14px}
.calc-check input{margin-top:3px}
.calc-tabs{display:flex;gap:8px;margin-top:4px}
.calc-tabs button{font:inherit;font-size:13px;font-weight:700;padding:8px 12px;border-radius:999px;border:1px solid var(--line);background:var(--bg);cursor:pointer;color:var(--ink)}
.calc-tabs button[aria-pressed=true]{border-color:var(--orange);background:var(--orange-soft)}
.calc-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:18px}
.calc-summary div{padding:14px;border-radius:12px;background:var(--bg)}
.calc-summary span{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.calc-summary strong{display:block;margin-top:4px;font-size:20px}
.calc-verdict{margin-top:14px;padding:14px 16px;border-radius:12px;font-weight:700;font-size:15px;background:#e8f5ec;color:#1d7a3a}
.calc-verdict.warn{background:#fff4e0;color:#8a5a00}
.calc-note{margin:12px 0 0;font-size:13px;color:var(--muted);line-height:1.6}
.rto-plan{margin-top:16px;display:flex;flex-direction:column;gap:10px}
.rto-day{border:1px solid var(--line);border-radius:12px;padding:12px 14px}
.rto-day h3{margin:0 0 6px;font-size:16px}
.rto-day ul{margin:0;padding-left:18px;font-size:14px;line-height:1.6}
.rto-rest{border-radius:12px;padding:10px 14px;background:var(--bg);font-size:14px}
.rto-rest.weekly{background:var(--orange-soft)}
.rto-drive{color:var(--ink)}.rto-break{color:var(--muted)}
@media (max-width:760px){.calc-row,.calc-summary{grid-template-columns:1fr}.calc-card{padding:20px}}
"""


def _page_js() -> str:
    return PLANNER_JS + r"""
(function(){
  const L = JSON.parse(document.getElementById('rto-data').textContent);
  const $ = s => document.querySelector(s);
  const num = v => { const x = parseFloat(String(v).replace(',', '.')); return isFinite(x) ? x : NaN; };
  const hm = m => { m = Math.round(m); const h = Math.floor(m / 60), mm = m % 60; return h + ' ч' + (mm ? ' ' + String(mm).padStart(2, '0') + ' мин' : ''); };
  const dt = ms => new Date(ms).toLocaleString('ru-RU', {weekday:'short', day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'});
  const tm = ms => new Date(ms).toLocaleTimeString('ru-RU', {hour:'2-digit', minute:'2-digit'});
  let mode = 'time';
  function setMode(m){ mode = m; document.querySelectorAll('[data-mode]').forEach(b => b.setAttribute('aria-pressed', b.dataset.mode === m)); $('#rto-by-time').hidden = m !== 'time'; $('#rto-by-dist').hidden = m !== 'dist'; calc(); }
  function driveMinutes(){
    if (mode === 'time') { const h = num($('#rto-hours').value) || 0, m = num($('#rto-mins').value) || 0; return h * 60 + m; }
    const km = num($('#rto-km').value), v = num($('#rto-speed').value);
    return (isFinite(km) && isFinite(v) && v > 0) ? km / v * 60 : NaN;
  }
  function calc(){
    const drive = driveMinutes();
    const start = new Date($('#rto-start').value).getTime();
    const out = $('#rto-plan'), v = $('#rto-verdict');
    if (!isFinite(drive) || drive <= 0 || !isFinite(start)) { out.innerHTML = ''; v.className = 'calc-verdict warn'; v.textContent = 'Укажите время за рулём (или расстояние и среднюю скорость) и время выезда.'; ['#sum-arr','#sum-total','#sum-days'].forEach(s => $(s).textContent = '—'); return; }
    const p = planTrip({driveMin: drive, startMs: start, extDays: $('#rto-ext').checked ? 2 : 0, reducedRest: $('#rto-reduced').checked}, L);
    $('#sum-arr').textContent = dt(p.arrival);
    $('#sum-total').textContent = hm(p.totalMin);
    $('#sum-days').textContent = p.days;
    const notes = [];
    if (p.extDays) notes.push('дней по 10 ч за рулём: ' + p.extDays);
    if (p.reducedRests) notes.push('сокращённых отдыхов по 9 ч: ' + p.reducedRests);
    if (p.weeklyRests) notes.push('еженедельных отдыхов по 45 ч: ' + p.weeklyRests);
    v.className = 'calc-verdict';
    v.textContent = 'За рулём ' + hm(drive) + ', в пути с отдыхом ' + hm(p.totalMin) + '.' + (notes.length ? ' Учтено: ' + notes.join(', ') + '.' : '');
    out.innerHTML = p.events.map(e => {
      if (e.type === 'day') {
        const items = e.segments.map(s => s.kind === 'drive'
          ? '<li class="rto-drive">' + tm(s.start) + '–' + tm(s.end) + ' — за рулём ' + hm(s.min) + '</li>'
          : '<li class="rto-break">' + tm(s.start) + '–' + tm(s.end) + ' — перерыв 45 мин (можно 15 + 30)</li>').join('');
        return '<div class="rto-day"><h3>День ' + e.no + ' · ' + dt(e.start) + '</h3><ul>' + items + '</ul><p class="calc-note">За рулём за день: ' + hm(e.drive) + (e.extended ? ' (увеличенный день, до 10 ч)' : '') + '</p></div>';
      }
      if (e.type === 'rest') return '<div class="rto-rest">Ежедневный отдых ' + hm(e.min) + (e.reduced ? ' (сокращённый)' : '') + ': ' + dt(e.start) + ' — ' + dt(e.end) + '</div>';
      return '<div class="rto-rest weekly">Еженедельный отдых 45 ч: ' + dt(e.start) + ' — ' + dt(e.end) + '</div>';
    }).join('');
  }
  const now = new Date(); now.setMinutes(0, 0, 0); now.setHours(now.getHours() + 1);
  const pad = n => String(n).padStart(2, '0');
  $('#rto-start').value = now.getFullYear() + '-' + pad(now.getMonth() + 1) + '-' + pad(now.getDate()) + 'T' + pad(now.getHours()) + ':00';
  document.querySelectorAll('[data-mode]').forEach(b => b.addEventListener('click', () => setMode(b.dataset.mode)));
  document.querySelectorAll('#rto-form input').forEach(i => { i.addEventListener('input', calc); i.addEventListener('change', calc); });
  setMode('time');
})();
"""


def render_rto_calculator_page(base_url: str, telegram_cta: str) -> str:
    canonical = base_url + PAGE_PATH
    title = "Калькулятор режима труда и отдыха водителя 2026 — перерывы и отдых по приказу № 160"
    description = (
        "Бесплатный планировщик рейса по режиму труда и отдыха водителя: 9 часов за рулём, перерыв 45 минут после 4,5 часов, "
        "ежедневный отдых 11 часов и еженедельный 45 часов по приказу Минтранса № 160."
    )[:200]
    data_json = json.dumps(LIMITS, separators=(",", ":"))
    faq_html = "".join(
        f'<details class="regulation-faq__item"><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>' for q, a in FAQ
    )
    schema = json.dumps(
        [
            {
                "@context": "https://schema.org",
                "@type": "WebApplication",
                "name": "Калькулятор режима труда и отдыха водителя",
                "url": canonical,
                "applicationCategory": "BusinessApplication",
                "operatingSystem": "Any",
                "inLanguage": "ru-RU",
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "RUB"},
                "isBasedOn": ORDER_URL,
            },
            {
                "@context": "https://schema.org",
                "@type": "FAQPage",
                "mainEntity": [
                    {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ
                ],
            },
        ],
        ensure_ascii=False,
        separators=(",", ":"),
    ).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)} | СпецАвтоПортал</title>
  <meta name="description" content="{html.escape(description, quote=True)}" />
  <meta name="robots" content="index,follow,max-image-preview:large" />
  <link rel="canonical" href="{canonical}" />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="СпецАвтоПортал" />
  <meta property="og:title" content="{html.escape(title, quote=True)}" />
  <meta property="og:description" content="{html.escape(description, quote=True)}" />
  <meta property="og:url" content="{canonical}" />
  <link rel="stylesheet" href="/styles.css?v=30" />
  <link rel="icon" href="/spec_avtoportal_favicon.ico" type="image/x-icon" />
  <script type="application/ld+json">{schema}</script>
  <style>{_page_css()}</style>
</head>
<body class="regulation-page">
  <div class="topline"><div class="container topline-inner"><span>Профессиональное медиа о грузовой технике</span><span class="topline-dot"></span><span>Инструменты</span></div></div>
  <header class="site-header">
    <div class="container header-inner">
      <a href="/" class="brand" aria-label="СпецАвтоПортал — на главную">
        <span class="brand-mark" aria-hidden="true"><span></span><span></span></span>
        <span class="brand-copy"><strong>СпецАвтоПортал</strong><small>рынок · техника · регламенты</small></span>
      </a>
      <nav class="main-nav" aria-label="Основная навигация">
        <a href="/" class="nav-link">Новости</a>
        <a href="/brands/" class="nav-link">Бренды</a>
        <a href="/knowledge.html" class="nav-link">База знаний</a>
        <a href="/tools/" class="nav-link nav-link-active">Калькуляторы</a>
      </nav>
      <div class="header-socials" aria-label="Социальные сети">
        <a href="https://t.me/specavtoportal" class="header-social-link header-social-link--telegram" target="_blank" rel="noopener" aria-label="Telegram"><span class="social-full">Telegram</span><span class="social-short">TG</span></a>
        <a href="https://vk.ru/specavtoportal" class="header-social-link" target="_blank" rel="noopener" aria-label="VK"><span class="social-full">VK</span><span class="social-short">VK</span></a>
      </div>
    </div>
  </header>

  <main>
    <section class="regulation-hero">
      <div class="container">
        <p class="section-kicker"><a href="/knowledge.html">База знаний</a> · Инструменты</p>
        <h1>Калькулятор режима труда и отдыха водителя</h1>
        <p class="regulation-hero__title">Спланируйте рейс по нормам приказа Минтранса № 160: где остановиться на перерыв, когда отдыхать и во сколько вы приедете.</p>
      </div>
    </section>

    <section class="container regulation-layout">
      <article class="regulation-main">
        <section class="calc-card" id="calculator">
          <p class="section-kicker">Расчёт</p>
          <h2>Ваш рейс</h2>
          <form id="rto-form" onsubmit="return false">
            <div class="calc-tabs">
              <button type="button" data-mode="time" aria-pressed="true">Время за рулём</button>
              <button type="button" data-mode="dist" aria-pressed="false">Расстояние и скорость</button>
            </div>
            <div class="calc-row" id="rto-by-time">
              <label class="calc-field">Часов за рулём<input id="rto-hours" inputmode="numeric" value="20"></label>
              <label class="calc-field">Минут<input id="rto-mins" inputmode="numeric" value="0"></label>
            </div>
            <div class="calc-row" id="rto-by-dist" hidden>
              <label class="calc-field">Расстояние, км<input id="rto-km" inputmode="decimal" value="1500"></label>
              <label class="calc-field">Средняя скорость, км/ч<input id="rto-speed" inputmode="decimal" value="65"></label>
            </div>
            <div class="calc-row">
              <label class="calc-field">Выезд<input id="rto-start" type="datetime-local"></label>
            </div>
            <label class="calc-check"><input type="checkbox" id="rto-ext"> Использовать увеличенные дни до 10 часов за рулём (не чаще двух раз в неделю)</label>
            <label class="calc-check"><input type="checkbox" id="rto-reduced"> Сокращать ежедневный отдых до 9 часов (не более трёх раз между еженедельными отдыхами)</label>
          </form>
          <div class="calc-summary">
            <div><span>Прибытие</span><strong id="sum-arr">—</strong></div>
            <div><span>В пути с отдыхом</span><strong id="sum-total">—</strong></div>
            <div><span>Дней за рулём</span><strong id="sum-days">—</strong></div>
          </div>
          <div class="calc-verdict" id="rto-verdict" aria-live="polite">Заполните данные.</div>
          <div class="rto-plan" id="rto-plan"></div>
          <p class="calc-note">Расчёт считает, что рейс начинается после полноценного отдыха, а до рейса на этой неделе водитель ещё не ездил. Погрузка, оформление и другая работа тоже входят в рабочее время — закладывайте её отдельно. Недели считаются от начала рейса, а не по календарю.</p>
        </section>

        <section class="regulation-section">
          <p class="section-kicker">Нормы</p>
          <h2>Что учитывает калькулятор</h2>
          <ul>
            <li>за рулём — не более 9 часов в сутки, до 10 часов не чаще двух раз в неделю;</li>
            <li>не более 56 часов за неделю и 90 часов за две недели подряд;</li>
            <li>перерыв не менее 45 минут не позднее чем через 4 часа 30 минут управления;</li>
            <li>ежедневный отдых не менее 11 часов, сокращение до 9 часов — не более трёх раз между еженедельными отдыхами;</li>
            <li>еженедельный отдых не менее 45 часов — до начала седьмого рабочего дня.</li>
          </ul>
          <p>Подробный разбор норм, пример рабочего дня и штрафы по статье 11.23 КоАП — в статье <a href="/knowledge/rezhim-truda-i-otdyha-voditelya/">«Режим труда и отдыха водителя в 2026 году»</a>.</p>
        </section>

        {telegram_cta}

        <section class="regulation-section regulation-faq">
          <p class="section-kicker">Вопросы и ответы</p>
          <h2>Частые вопросы</h2>
          {faq_html}
        </section>

        <section class="regulation-section">
          <p class="section-kicker">По теме</p>
          <h2>Что ещё пригодится</h2>
          <ul>
            <li><a href="/knowledge/rezhim-truda-i-otdyha-voditelya/">Режим труда и отдыха водителя: нормы приказа № 160 и тахограф</a></li>
            <li><a href="/tools/nagruzka-na-os/">Калькулятор нагрузки на ось</a></li>
            <li><a href="/knowledge/shtraf-za-peregruz/">Штраф за перегруз в 2026 году</a></li>
            <li><a href="/regulations/mintrans-212-2026/">Новые правила безопасности перевозок с 1 сентября 2026</a></li>
          </ul>
        </section>
      </article>

      <aside class="regulation-sidebar">
        <section class="sidebar-block sidebar-dark">
          <p class="sidebar-eyebrow">Первоисточник</p>
          <h3>Приказ Минтранса России № 160 от 14.04.2026</h3>
          <p class="sidebar-text">Особенности режима рабочего времени и времени отдыха водителей автомобилей. Действует с 01.09.2026 до 01.09.2032.</p>
          <a class="partner-card__button" href="{ORDER_URL}" target="_blank" rel="noopener">Открыть текст приказа <span>↗</span></a>
        </section>
        <section class="sidebar-block">
          <p class="sidebar-eyebrow">Важно</p>
          <p class="sidebar-text">Калькулятор справочный и помогает спланировать рейс. Он не заменяет данные тахографа и текст нормативного акта. Для международных перевозок действуют правила ЕСТР.</p>
        </section>
      </aside>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/law.html">Нормативы</a><a href="/tools/nagruzka-na-os/">Калькулятор нагрузки</a><a href="{PAGE_PATH}">Калькулятор режима водителя</a><a href="/brands/">Бренды</a><a href="https://t.me/specavtoportal" target="_blank" rel="noopener">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
  <script type="application/json" id="rto-data">{data_json}</script>
  <script>{_page_js()}</script>
</body>
</html>
"""
