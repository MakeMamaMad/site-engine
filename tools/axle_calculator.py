"""Axle load calculator page: /tools/nagruzka-na-os/.

Limits come from the Rules for heavy and oversized vehicles approved by
Government Decree No. 2060 of 01.12.2023:
  * Appendix 2 "Допустимая нагрузка на ось транспортного средства";
  * Appendix 3 "Допустимая масса транспортного средства".

Values for single axles and for groups of 4+ closely spaced axles are PER
AXLE; values for double and triple groups are for the WHOLE GROUP (the
decree's note: the group value is divided by the number of axles).
Every column is (road for 6 t/axle, 10 t/axle, 11.5 t/axle); the pair is
(single tyres, dual tyres).
"""
from __future__ import annotations

import html
import json
from typing import Any

OFFICIAL_URL = "http://publication.pravo.gov.ru/document/0001202312010117"
PAGE_PATH = "/tools/nagruzka-na-os/"

ROAD_CLASSES = [6, 10, 11.5]
SPACING_BANDS = ["lt1", "1-1.3", "1.3-1.8", "1.8-2.5"]

# group type -> tyres ("single"|"dual") -> band -> [6 t, 10 t, 11.5 t]
AXLE_LIMITS: dict[str, Any] = {
    "single": {  # per axle, distance to neighbouring axle > 2.5 m
        "single": {"any": [5.5, 9, 10.5]},
        "dual": {"any": [6, 10, 11.5]},
    },
    "double": {  # whole group
        "single": {"lt1": [8, 10, 11.5], "1-1.3": [9, 13, 14], "1.3-1.8": [10, 15, 17], "1.8-2.5": [11, 17, 18]},
        "dual": {"lt1": [9, 11, 12.5], "1-1.3": [10, 14, 16], "1.3-1.8": [11, 16, 18], "1.8-2.5": [12, 18, 20]},
    },
    "triple": {  # whole group
        "single": {"lt1": [11, 15, 17], "1-1.3": [12, 18, 20], "1.3-1.8": [13.5, 21, 23.5], "1.8-2.5": [15, 22, 25]},
        "dual": {"lt1": [12, 16.5, 18], "1-1.3": [13, 19.5, 21], "1.3-1.8": [15, 22.5, 24], "1.8-2.5": [16, 23, 26]},
    },
    "multi": {  # groups of more than three axles, per axle
        "single": {"lt1": [3.5, 5, 5.5], "1-1.3": [4, 6, 6.5], "1.3-1.8": [4.5, 6.5, 7.5], "1.8-2.5": [5, 7, 8.5]},
        "dual": {"lt1": [4, 5.5, 6], "1-1.3": [4.5, 6.5, 7], "1.3-1.8": [5, 7, 8], "1.8-2.5": [5.5, 7.5, 9]},
    },
}

# vehicle kind -> axle count -> tonnes (the last key applies to "and more")
MASS_LIMITS = {
    "truck": {2: 18, 3: 25, 4: 32, 5: 38},
    "train": {3: 28, 4: 36, 5: 40, 6: 44},
}

PRESETS = [
    {
        "id": "tractor-4x2-tri",
        "name": "Тягач 4×2 + полуприцеп 3 оси",
        "kind": "train",
        "groups": [
            {"type": "single", "tyres": "single", "spacing": "", "load": 7},
            {"type": "single", "tyres": "dual", "spacing": "", "load": 9.8},
            {"type": "triple", "tyres": "single", "spacing": "1,31", "load": 20.5},
        ],
    },
    {
        "id": "tractor-6x4-tri",
        "name": "Тягач 6×4 + полуприцеп 3 оси",
        "kind": "train",
        "groups": [
            {"type": "single", "tyres": "single", "spacing": "", "load": 7.5},
            {"type": "double", "tyres": "dual", "spacing": "1,35", "load": 15},
            {"type": "triple", "tyres": "single", "spacing": "1,31", "load": 21},
        ],
    },
    {
        "id": "dump-6x4",
        "name": "Самосвал 6×4",
        "kind": "truck",
        "groups": [
            {"type": "single", "tyres": "single", "spacing": "", "load": 8},
            {"type": "double", "tyres": "dual", "spacing": "1,4", "load": 16},
        ],
    },
    {
        "id": "truck-4x2",
        "name": "Двухосный грузовик",
        "kind": "truck",
        "groups": [
            {"type": "single", "tyres": "single", "spacing": "", "load": 6},
            {"type": "single", "tyres": "dual", "spacing": "", "load": 10},
        ],
    },
]

FAQ = [
    (
        "Какая допустимая нагрузка на ось грузовика?",
        "Для одиночной оси с двускатными колёсами — 6 т на дорогах, рассчитанных на 6 т/ось, 10 т на дорогах 10 т/ось и 11,5 т на дорогах 11,5 т/ось. "
        "С односкатными колёсами — 5,5, 9 и 10,5 т. Ось считается одиночной, если до соседней оси больше 2,5 м.",
    ),
    (
        "Сколько можно на тележку полуприцепа из трёх осей?",
        "Для строенных осей с расстоянием между ними от 1,3 до 1,8 м и односкатными колёсами — 21 т на всю тележку на дороге 10 т/ось "
        "и 23,5 т на дороге 11,5 т/ось; с двускатными колёсами — 22,5 и 24 т. На каждую ось — значение группы, делённое на три.",
    ),
    (
        "Какая допустимая масса автопоезда?",
        "Для седельных и прицепных автопоездов: 3 оси — 28 т, 4 оси — 36 т, 5 осей — 40 т, 6 и более осей — 44 т. "
        "Для одиночных автомобилей: 2 оси — 18 т, 3 оси — 25 т, 4 оси — 32 т, 5 и более осей — 38 т.",
    ),
    (
        "Как узнать, на какую нагрузку рассчитана дорога?",
        "Федеральные трассы в основном рассчитаны на 11,5 т/ось, многие региональные и местные дороги — на 10 или 6 т/ось. "
        "Если на дороге стоит знак ограничения массы или нагрузки на ось, действует значение на знаке. Весной вводятся временные ограничения.",
    ),
    (
        "Нужно ли спецразрешение при превышении?",
        "Да. Транспортное средство, у которого масса или нагрузка на ось больше допустимых, считается тяжеловесным, и для движения ему нужно специальное разрешение.",
    ),
]


def _page_css() -> str:
    return """
.calc-card{margin-top:14px;padding:26px;border:1px solid var(--line);border-radius:16px;background:var(--paper)}
.calc-card h2{margin:6px 0 14px;font-size:26px;line-height:1.1;letter-spacing:-.03em}
.calc-row{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.calc-field{display:flex;flex-direction:column;gap:6px;font-size:13px;color:var(--muted)}
.calc-field{min-width:0}
.calc-field select,.calc-field input{font:inherit;font-size:15px;color:var(--ink);padding:10px 12px;border:1px solid var(--line);border-radius:10px;background:#fff;min-width:0;width:100%;box-sizing:border-box}
.calc-presets{display:flex;flex-wrap:wrap;gap:8px;margin-top:14px}
.calc-presets button,.calc-add{font:inherit;font-size:13px;font-weight:700;padding:8px 12px;border-radius:999px;border:1px solid var(--line);background:var(--bg);cursor:pointer;color:var(--ink)}
.calc-presets button:hover,.calc-add:hover{border-color:var(--orange)}
.calc-group{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,1.1fr) minmax(0,.8fr) minmax(0,.8fr) auto;gap:10px;align-items:end;padding:14px 0;border-top:1px solid var(--line)}
.calc-group:first-of-type{border-top:0}
.calc-group .calc-remove{font:inherit;border:0;background:none;color:var(--muted);cursor:pointer;font-size:20px;padding:8px}
.calc-group__result{grid-column:1/-1;font-size:14px;line-height:1.5;padding:10px 12px;border-radius:10px;background:var(--bg)}
.calc-ok{color:#1d7a3a}.calc-bad{color:#b3261e}.calc-warn{color:#8a5a00}
.calc-summary{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:6px}
.calc-summary div{padding:14px;border-radius:12px;background:var(--bg)}
.calc-summary span{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}
.calc-summary strong{display:block;margin-top:4px;font-size:20px}
.calc-verdict{margin-top:14px;padding:14px 16px;border-radius:12px;font-weight:700;font-size:15px}
.calc-verdict.ok{background:#e8f5ec;color:#1d7a3a}.calc-verdict.bad{background:#fdecea;color:#b3261e}
.calc-note{margin:12px 0 0;font-size:13px;color:var(--muted);line-height:1.6}
.calc-table{width:100%;border-collapse:collapse;font-size:14px;margin-top:8px}
.calc-table th,.calc-table td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left}
.calc-table th{font-size:12px;color:var(--muted);font-weight:700}
.calc-scroll{overflow-x:auto}
@media (max-width:760px){
 .calc-row,.calc-summary{grid-template-columns:1fr}
 .calc-group{grid-template-columns:minmax(0,1fr) minmax(0,1fr)}
 .calc-group .calc-remove{justify-self:end}
 .calc-card{padding:20px}
}
"""


def _page_js() -> str:
    # Plain JS, no dependencies. Numbers are rounded to 0.01 t for display.
    return r"""
(function(){
  const D = JSON.parse(document.getElementById('axle-data').textContent);
  const $ = s => document.querySelector(s);
  const groupsEl = $('#calc-groups');
  const TYPES = {single:'Одиночная ось', double:'Сдвоенные оси', triple:'Строенные оси', multi:'Группа из 4+ осей'};
  const AXLES = {single:1, double:2, triple:3};
  const fmt = n => { const r = Math.round(n*100)/100; return (Object.is(r, -0) ? 0 : r).toLocaleString('ru-RU'); };
  const num = v => { const x = parseFloat(String(v).replace(',', '.')); return isFinite(x) ? x : NaN; };
  function band(d){ if (d < 1) return 'lt1'; if (d < 1.3) return '1-1.3'; if (d < 1.8) return '1.3-1.8'; if (d <= 2.5) return '1.8-2.5'; return null; }
  function row(g){
    const el = document.createElement('div'); el.className = 'calc-group';
    el.innerHTML =
      '<label class="calc-field">Тип<select data-k="type">' + Object.entries(TYPES).map(([k,v]) => '<option value="'+k+'">'+v+'</option>').join('') + '</select></label>' +
      '<label class="calc-field">Колёса<select data-k="tyres"><option value="single">Односкатные</option><option value="dual">Двускатные</option></select></label>' +
      '<label class="calc-field" data-f="spacing">Между осями, м<input data-k="spacing" inputmode="decimal" placeholder="1,31"></label>' +
      '<label class="calc-field" data-f="count">Осей в группе<input data-k="count" inputmode="numeric" value="4"></label>' +
      '<label class="calc-field">Нагрузка, т<input data-k="load" inputmode="decimal" placeholder="на группу"></label>' +
      '<button type="button" class="calc-remove" aria-label="Удалить">×</button>' +
      '<div class="calc-group__result" aria-live="polite"></div>';
    el.querySelector('[data-k=type]').value = g.type || 'single';
    el.querySelector('[data-k=tyres]').value = g.tyres || 'single';
    el.querySelector('[data-k=spacing]').value = g.spacing || '';
    el.querySelector('[data-k=load]').value = g.load != null ? String(g.load).replace('.', ',') : '';
    if (g.count) el.querySelector('[data-k=count]').value = g.count;
    el.addEventListener('input', calc); el.addEventListener('change', calc);
    el.querySelector('.calc-remove').addEventListener('click', () => { el.remove(); calc(); });
    groupsEl.appendChild(el);
  }
  function load(preset){ groupsEl.innerHTML = ''; $('#calc-kind').value = preset.kind; preset.groups.forEach(row); calc(); }
  function calc(){
    const road = D.roads.indexOf(num($('#calc-road').value));
    const kind = $('#calc-kind').value;
    let axles = 0, total = 0, bad = 0, missing = 0;
    groupsEl.querySelectorAll('.calc-group').forEach(el => {
      const get = k => el.querySelector('[data-k='+k+']').value;
      const type = get('type'), tyres = get('tyres');
      el.querySelector('[data-f=spacing]').style.display = type === 'single' ? 'none' : '';
      el.querySelector('[data-f=count]').style.display = type === 'multi' ? '' : 'none';
      const n = type === 'multi' ? Math.max(4, Math.round(num(get('count')) || 4)) : AXLES[type];
      axles += n;
      const out = el.querySelector('.calc-group__result');
      let limit, perAxle;
      if (type === 'single') { limit = D.limits.single[tyres].any[road]; perAxle = limit; }
      else {
        const d = num(get('spacing'));
        if (!isFinite(d)) { out.innerHTML = '<span class="calc-warn">Укажите расстояние между осями группы.</span>'; missing++; return; }
        const b = band(d);
        if (!b) { out.innerHTML = '<span class="calc-warn">При расстоянии больше 2,5 м оси считаются одиночными — добавьте их как одиночные.</span>'; missing++; return; }
        const v = D.limits[type][tyres][b][road];
        if (type === 'multi') { perAxle = v; limit = v * n; } else { limit = v; perAxle = v / n; }
      }
      const fact = num(get('load'));
      if (!isFinite(fact)) { out.innerHTML = 'Допустимо: <b>' + fmt(limit) + ' т</b>' + (n > 1 ? ' на группу, ' + fmt(perAxle) + ' т на ось' : '') + '. Введите нагрузку, чтобы проверить.'; missing++; return; }
      total += fact;
      const diff = Math.round((fact - limit) * 1000) / 1000, pct = diff / limit * 100;
      if (diff > 0) { bad++; out.innerHTML = '<span class="calc-bad">Перегруз ' + fmt(diff) + ' т (' + fmt(pct) + '%).</span> Допустимо ' + fmt(limit) + ' т' + (n > 1 ? ' на группу (' + fmt(perAxle) + ' т на ось)' : '') + ', факт ' + fmt(fact) + ' т.'; }
      else { out.innerHTML = '<span class="calc-ok">' + (diff === 0 ? 'В норме, ровно на пределе.' : 'В норме, запас ' + fmt(-diff) + ' т.') + '</span> Допустимо ' + fmt(limit) + ' т' + (n > 1 ? ' на группу (' + fmt(perAxle) + ' т на ось)' : '') + ', факт ' + fmt(fact) + ' т.'; }
    });
    const table = D.mass[kind]; const keys = Object.keys(table).map(Number).sort((a,b) => a-b);
    let massLimit = NaN;
    if (axles >= keys[0]) { const k = keys.filter(x => x <= axles).pop(); massLimit = table[k]; }
    $('#sum-axles').textContent = axles;
    $('#sum-mass').textContent = missing ? '—' : fmt(total) + ' т';
    $('#sum-limit').textContent = isFinite(massLimit) ? fmt(massLimit) + ' т' : '—';
    const v = $('#calc-verdict');
    const massBad = isFinite(massLimit) && !missing && total > massLimit;
    if (missing) { v.className = 'calc-verdict'; v.textContent = 'Заполните все группы осей, чтобы получить итог.'; }
    else if (bad || massBad) {
      v.className = 'calc-verdict bad';
      v.textContent = 'Тяжеловесное ТС: ' + [bad ? 'перегруз на ' + bad + ' ' + (bad === 1 ? 'группе осей' : 'группах осей') : '', massBad ? 'масса больше допустимой на ' + fmt(total - massLimit) + ' т' : ''].filter(Boolean).join('; ') + '. Нужна перегрузка или специальное разрешение.';
    } else if (!isFinite(massLimit)) { v.className = 'calc-verdict'; v.textContent = 'Для такого количества осей допустимая масса в таблице не указана — проверьте тип ТС.'; }
    else { v.className = 'calc-verdict ok'; v.textContent = 'В пределах допустимых нагрузок и массы для выбранной дороги.'; }
  }
  document.querySelectorAll('[data-preset]').forEach(b => b.addEventListener('click', () => load(D.presets.find(p => p.id === b.dataset.preset))));
  $('#calc-add').addEventListener('click', () => { row({type:'single', tyres:'single'}); calc(); });
  $('#calc-road').addEventListener('change', calc); $('#calc-kind').addEventListener('change', calc);
  load(D.presets[0]);
})();
"""


def _limits_table_html() -> str:
    labels = {"lt1": "до 1 м", "1-1.3": "1–1,3 м", "1.3-1.8": "1,3–1,8 м", "1.8-2.5": "1,8–2,5 м"}
    rows = []

    def cell(pair: list[float], dual: list[float]) -> str:
        return " / ".join(f"{str(a).replace('.', ',')} ({str(b).replace('.', ',')})" for a, b in zip(pair, dual))

    rows.append(("Одиночная ось", "более 2,5 м до соседней", cell(AXLE_LIMITS["single"]["single"]["any"], AXLE_LIMITS["single"]["dual"]["any"]), "на ось"))
    for key, name, unit in (("double", "Сдвоенные оси", "на группу"), ("triple", "Строенные оси", "на группу"), ("multi", "Группа из 4+ осей", "на каждую ось")):
        for band in SPACING_BANDS:
            rows.append((name, labels[band], cell(AXLE_LIMITS[key]["single"][band], AXLE_LIMITS[key]["dual"][band]), unit))
    body = "".join(
        f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td><td>{html.escape(d)}</td></tr>"
        for a, b, c, d in rows
    )
    return (
        '<div class="calc-scroll"><table class="calc-table"><thead><tr><th>Оси</th><th>Расстояние между осями</th>'
        "<th>Дороги 6 / 10 / 11,5 т на ось, т</th><th>Значение</th></tr></thead>"
        f"<tbody>{body}</tbody></table></div>"
        '<p class="calc-note">Без скобок — односкатные колёса, в скобках — двускатные. Смешанные колёса считаются односкатными.</p>'
    )


def render_axle_calculator_page(base_url: str, telegram_cta: str) -> str:
    canonical = base_url + PAGE_PATH
    title = "Калькулятор нагрузки на ось автопоезда 2026 — онлайн-проверка по ПП № 2060"
    description = (
        "Бесплатный калькулятор нагрузки на оси грузовика и автопоезда: допустимые нагрузки на одиночные, сдвоенные и строенные оси "
        "и допустимая масса по постановлению Правительства № 2060 для дорог 6, 10 и 11,5 т/ось."
    )[:200]
    data = {
        "roads": ROAD_CLASSES,
        "limits": AXLE_LIMITS,
        "mass": {k: {str(n): v for n, v in table.items()} for k, table in MASS_LIMITS.items()},
        "presets": PRESETS,
    }
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    presets_html = "".join(
        f'<button type="button" data-preset="{html.escape(p["id"], quote=True)}">{html.escape(p["name"])}</button>' for p in PRESETS
    )
    faq_html = "".join(
        f'<details class="regulation-faq__item"><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>' for q, a in FAQ
    )
    schema = json.dumps(
        [
            {
                "@context": "https://schema.org",
                "@type": "WebApplication",
                "name": "Калькулятор нагрузки на ось",
                "url": canonical,
                "applicationCategory": "BusinessApplication",
                "operatingSystem": "Any",
                "inLanguage": "ru-RU",
                "offers": {"@type": "Offer", "price": "0", "priceCurrency": "RUB"},
                "isBasedOn": OFFICIAL_URL,
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
        <a href="/tools/nagruzka-na-os/" class="nav-link nav-link-active">Калькулятор</a>
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
        <h1>Калькулятор нагрузки на ось</h1>
        <p class="regulation-hero__title">Проверьте, укладывается ли грузовик или автопоезд в допустимые нагрузки на оси и общую массу — по постановлению Правительства № 2060.</p>
      </div>
    </section>

    <section class="container regulation-layout">
      <article class="regulation-main">
        <section class="calc-card" id="calculator">
          <p class="section-kicker">Расчёт</p>
          <h2>Ваш автомобиль или автопоезд</h2>
          <div class="calc-row">
            <label class="calc-field">Дорога рассчитана на
              <select id="calc-road"><option value="6">6 т на ось</option><option value="10" selected>10 т на ось</option><option value="11.5">11,5 т на ось</option></select>
            </label>
            <label class="calc-field">Транспортное средство
              <select id="calc-kind"><option value="train">Автопоезд (седельный или прицепной)</option><option value="truck">Одиночный автомобиль</option></select>
            </label>
          </div>
          <p class="calc-note">Типовая схема — затем поправьте нагрузки на свои:</p>
          <div class="calc-presets">{presets_html}</div>
          <div id="calc-groups" style="margin-top:14px"></div>
          <button type="button" class="calc-add" id="calc-add">+ Добавить ось или группу осей</button>
          <div class="calc-summary" style="margin-top:18px">
            <div><span>Всего осей</span><strong id="sum-axles">—</strong></div>
            <div><span>Фактическая масса</span><strong id="sum-mass">—</strong></div>
            <div><span>Допустимая масса</span><strong id="sum-limit">—</strong></div>
          </div>
          <div class="calc-verdict" id="calc-verdict" aria-live="polite">Заполните данные.</div>
          <p class="calc-note">Не знаете нагрузки по осям? Посчитайте их по массе и положению груза в <a href="/tools/raspredelenie-gruza-po-osyam/">калькуляторе распределения груза</a>.</p>
          <p class="calc-note">Для сдвоенных и строенных осей вводите нагрузку на всю группу, для группы из 4+ осей — тоже на всю группу. Если на дороге стоит знак ограничения массы или нагрузки, действует значение на знаке. Весной на региональных дорогах вводятся временные ограничения.</p>
        </section>

        <section class="regulation-section">
          <p class="section-kicker">Как пользоваться</p>
          <h2>Три шага</h2>
          <ol>
            <li>Выберите, на какую нагрузку рассчитана дорога: федеральные трассы в основном 11,5 т/ось, региональные и местные — 10 или 6 т/ось.</li>
            <li>Опишите оси: одиночная ось — если до соседней больше 2,5 м; сдвоенные и строенные — с расстоянием между осями группы.</li>
            <li>Введите нагрузку по результатам взвешивания или расчёта загрузки. Калькулятор покажет запас или перегруз по каждой группе и по общей массе.</li>
          </ol>
        </section>

        <section class="regulation-section">
          <p class="section-kicker">Нормы</p>
          <h2>Допустимые нагрузки на оси</h2>
          {_limits_table_html()}
          <p class="calc-note">Допустимая масса: одиночные автомобили — 2 оси 18 т, 3 оси 25 т, 4 оси 32 т, 5 и более 38 т; автопоезда — 3 оси 28 т, 4 оси 36 т, 5 осей 40 т, 6 и более 44 т.</p>
        </section>

        {telegram_cta}

        <section class="regulation-section regulation-faq">
          <p class="section-kicker">Вопросы и ответы</p>
          <h2>Частые вопросы</h2>
          {faq_html}
        </section>

        <section class="regulation-section">
          <p class="section-kicker">По теме</p>
          <h2>Что почитать</h2>
          <ul>
            <li><a href="/knowledge/nagruzka-na-os/">Нагрузка на ось: как проверить автопоезд перед рейсом</a></li>
            <li><a href="/knowledge/gabarity-i-massy/">Габариты и массы автопоезда: основные пределы</a></li>
            <li><a href="/tools/shtraf-za-peregruz/">Калькулятор штрафа за перегруз</a></li>
            <li><a href="/knowledge/shtraf-za-peregruz/">Штраф за перегруз в 2026 году: суммы по статье 12.21.1 КоАП</a></li>
            <li><a href="/knowledge/specrazreshenie-tyazhelovesnoe-ts/">Спецразрешение на тяжеловесный транспорт</a></li>
            <li><a href="/tools/raspredelenie-gruza-po-osyam/">Калькулятор распределения груза по осям тягача и полуприцепа</a></li>
            <li><a href="/knowledge/nagruzka-na-osi-evrofury/">Нагрузка на оси еврофуры и семиосного автопоезда</a></li>
            <li><a href="/knowledge/vynesennaya-os-polupricepa/">Вынесенная ось полуприцепа: сколько даёт по нагрузке</a></li>
            <li><a href="/tools/rezhim-truda-i-otdyha/">Калькулятор режима труда и отдыха водителя</a></li>
            <li><a href="/regulations/mintrans-212-2026/">Новые правила безопасности перевозок с 1 сентября 2026</a></li>
          </ul>
        </section>
      </article>

      <aside class="regulation-sidebar">
        <section class="sidebar-block sidebar-dark">
          <p class="sidebar-eyebrow">Первоисточник</p>
          <h3>Постановление Правительства РФ № 2060 от 01.12.2023</h3>
          <p class="sidebar-text">Правила движения тяжеловесного и (или) крупногабаритного транспортного средства, приложения 2 и 3.</p>
          <a class="partner-card__button" href="{OFFICIAL_URL}" target="_blank" rel="noopener">Открыть официальный документ <span>↗</span></a>
        </section>
        <section class="sidebar-block">
          <p class="sidebar-eyebrow">Важно</p>
          <p class="sidebar-text">Калькулятор справочный и не заменяет взвешивание и текст нормативного акта. Результаты контроля определяются по показаниям весового оборудования.</p>
        </section>
      </aside>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/law.html">Нормативы</a><a href="/tools/nagruzka-na-os/">Калькулятор нагрузки</a><a href="/guides.html">Гайды</a><a href="/brands/">Бренды</a><a href="https://t.me/specavtoportal" target="_blank" rel="noopener">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
  <script type="application/json" id="axle-data">{data_json}</script>
  <script>{_page_js()}</script>
</body>
</html>
"""
