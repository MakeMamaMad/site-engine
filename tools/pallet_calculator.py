"""Pallet loading calculator: /tools/skolko-pallet-v-furu/.

How many pallets fit on the floor of a body: rows of pallets either
"lengthwise" (long side along the body) or "crosswise" (long side across);
the best mix of the two row types is found by brute force. Stacking and
the payload limit cap the result. Plain JS (PALLET_JS), tested with node.
"""
from __future__ import annotations

import html
import json

from load_distribution_calculator import _page_css as _dist_css

PAGE_PATH = "/tools/skolko-pallet-v-furu/"

BODIES = [
    {"id": "tent", "name": "Еврофура (тент) 13,6 м", "length": 13.6, "width": 2.45, "payload": 20},
    {"id": "reefer", "name": "Рефрижератор 13,3 м", "length": 13.3, "width": 2.46, "payload": 20},
    {"id": "jumbo", "name": "Jumbo / мега 13,6 м", "length": 13.6, "width": 2.45, "payload": 20},
    {"id": "c40", "name": "Контейнер 40 футов", "length": 12.03, "width": 2.35, "payload": 26},
    {"id": "c20", "name": "Контейнер 20 футов", "length": 5.9, "width": 2.35, "payload": 21},
    {"id": "truck", "name": "Грузовик с кузовом 7,2 м", "length": 7.2, "width": 2.45, "payload": 10},
]

PALLETS = [
    {"id": "eur", "name": "Европаллета EUR 1200×800", "a": 1.2, "b": 0.8},
    {"id": "fin", "name": "Финская FIN 1200×1000", "a": 1.2, "b": 1.0},
    {"id": "us", "name": "Американская 1219×1016 (48×40″)", "a": 1.219, "b": 1.016},
    {"id": "half", "name": "Полупаллета 800×600", "a": 0.8, "b": 0.6},
]

PALLET_JS = r"""
// Best floor layout of a×b pallets in a body length L × width W (metres).
// Two guillotine layouts are tried and the better one is kept:
//  rows  — the body is cut into rows across its width; each row holds pallets
//          either long side across ("поперёк") or long side along ("вдоль");
//  lanes — the body is cut into lanes along its length; a lane as wide as the
//          long side holds pallets crosswise, one as wide as the short side —
//          lengthwise (this is how 24–25 EUR fit into a 40-ft container).
function palletFloor(L, W, a, b){
  const eps = 1e-9, long = Math.max(a, b), short = Math.min(a, b);
  const fl = x => Math.floor(x + eps);
  const across = {per: fl(W / long), depth: short}, along = {per: fl(W / short), depth: long};
  let best = {count: 0, mode: 'rows', rows: [0, 0], lanes: [0, 0], used: 0, long, short};
  const maxA = across.per > 0 ? fl(L / across.depth) : 0;
  for (let i = 0; i <= maxA; i++){
    const j = along.per > 0 ? fl((L - i * across.depth) / along.depth) : 0;
    const count = i * across.per + j * along.per, used = i * across.depth + j * along.depth;
    if (count > best.count || (count === best.count && best.mode === 'rows' && used < best.used))
      best = {count, mode: 'rows', rows: [i, j], perRow: [across.per, along.per], used, long, short};
  }
  const inWide = fl(L / short), inNarrow = fl(L / long);   // pallets per lane
  for (let n1 = 0; n1 * long <= W + eps; n1++){
    const n2 = fl((W - n1 * long) / short);
    const count = n1 * inWide + n2 * inNarrow;
    if (n1 > 0 && n2 > 0 && count > best.count)
      best = {count, mode: 'lanes', lanes: [n1, n2], perLane: [inWide, inNarrow], used: Math.max(n1 ? inWide * short : 0, n2 ? inNarrow * long : 0), long, short};
  }
  return best;
}

// Total pallets: floor layout × tiers, capped by payload (t) and pallet mass (kg).
function palletTotal(floor, tiers, payloadT, palletKg){
  const bySpace = floor * Math.max(1, tiers);
  const byMass = palletKg > 0 ? Math.floor(payloadT * 1000 / palletKg + 1e-9) : Infinity;
  return {bySpace, byMass, total: Math.min(bySpace, byMass), limitedBy: byMass < bySpace ? 'mass' : 'space'};
}
"""

FAQ = [
    (
        "Сколько европаллет помещается в еврофуру?",
        "В кузов 13,6 × 2,45 м: 33 европаллеты 1200×800, если ставить их вдоль по три в ряд, и до 34 при комбинированной расстановке "
        "(часть рядов — поперёк по две). Фактическое количество зависит от внутренних размеров кузова и способа погрузки.",
    ),
    (
        "Сколько финских паллет в еврофуру?",
        "Финских паллет 1200×1000 — 26 штук: по две поперёк кузова, 13 рядов по 1 м.",
    ),
    (
        "Сколько паллет в 40-футовый контейнер?",
        "В 40-футовый контейнер (внутри около 12,03 × 2,35 м) теоретически входит до 25 европаллет и до 22 финских, если ставить "
        "одну полосу поперёк и одну вдоль. Паллеты встают почти без зазора, поэтому на практике обычно грузят 23–24 и 20–21.",
    ),
    (
        "Почему важна масса, а не только место?",
        "Тяжёлые паллеты закончат грузоподъёмность раньше, чем место на полу. К тому же груз нужно распределить по длине кузова, "
        "чтобы не перегрузить отдельные оси — это можно проверить в калькуляторе распределения груза.",
    ),
]


def pallet_floor(length: float, width: float, a: float, b: float) -> int:
    """Python twin of palletFloor() in PALLET_JS (count only), for the static table."""
    eps = 1e-9
    long_, short = max(a, b), min(a, b)
    def fl(x: float) -> int:
        return int((x + eps) // 1)

    across, along = fl(width / long_), fl(width / short)
    best = 0
    if across > 0:
        for i in range(fl(length / short) + 1):
            j = fl((length - i * short) / long_) if along > 0 else 0
            best = max(best, i * across + j * along)
    elif along > 0:
        best = fl(length / long_) * along
    n1 = 1
    while n1 * long_ <= width + eps:
        n2 = fl((width - n1 * long_) / short)
        if n2 > 0:
            best = max(best, n1 * fl(length / short) + n2 * fl(length / long_))
        n1 += 1
    return best


def _table_rows() -> str:
    eur = next(p for p in PALLETS if p["id"] == "eur")
    fin = next(p for p in PALLETS if p["id"] == "fin")
    return "".join(
        f"<tr><td>{html.escape(b['name'])}</td><td>{pallet_floor(b['length'], b['width'], eur['a'], eur['b'])}</td>"
        f"<td>{pallet_floor(b['length'], b['width'], fin['a'], fin['b'])}</td></tr>"
        for b in BODIES
    )


def _page_js() -> str:
    return PALLET_JS + r"""
(function(){
  const D = JSON.parse(document.getElementById('pallet-data').textContent);
  const $ = s => document.querySelector(s);
  const num = v => { const x = parseFloat(String(v).replace(',', '.')); return isFinite(x) ? x : NaN; };
  const fmt = n => (Math.round(n*100)/100).toLocaleString('ru-RU');
  const plural = (n, one, few, many) => { const m10 = n % 10, m100 = n % 100; return m10 === 1 && m100 !== 11 ? one : (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) ? few : many; };
  const pal = n => n + ' ' + plural(n, 'паллета', 'паллеты', 'паллет');
  function setBody(){ const b = D.bodies.find(x => x.id === $('#p-body').value); if (!b) return;
    $('#p-L').value = String(b.length).replace('.', ','); $('#p-W').value = String(b.width).replace('.', ','); $('#p-payload').value = String(b.payload).replace('.', ','); calc(); }
  function setPallet(){ const p = D.pallets.find(x => x.id === $('#p-type').value); if (!p) return;
    $('#p-a').value = String(p.a).replace('.', ','); $('#p-b').value = String(p.b).replace('.', ','); calc(); }
  function calc(){
    const L = num($('#p-L').value), W = num($('#p-W').value), a = num($('#p-a').value), b = num($('#p-b').value);
    const tiers = Math.max(1, Math.round(num($('#p-tiers').value)) || 1), payload = num($('#p-payload').value), kg = num($('#p-kg').value);
    const out = $('#calc-verdict'), more = $('#p-more'), svg = $('#p-scheme');
    if (![L, W, a, b].every(x => x > 0)) { out.className = 'calc-verdict'; out.textContent = 'Заполните размеры кузова и паллеты.'; more.innerHTML = ''; svg.innerHTML = ''; return; }
    const f = palletFloor(L, W, a, b);
    const t = palletTotal(f.count, tiers, isFinite(payload) ? payload : Infinity, isFinite(kg) ? kg : 0);
    out.className = 'calc-verdict ok';
    out.textContent = 'Помещается ' + pal(t.total) + (tiers > 1 ? ' (' + f.count + ' на полу × ' + tiers + ' ' + plural(tiers, 'ярус', 'яруса', 'ярусов') + ')' : '') + (t.limitedBy === 'mass' ? ' — ограничивает грузоподъёмность' : '') + '.';
    let layout;
    if (f.mode === 'lanes') layout = f.lanes[0] + ' ' + plural(f.lanes[0], 'полоса', 'полосы', 'полос') + ' по ' + f.perLane[0] + ' поперёк + ' + f.lanes[1] + ' ' + plural(f.lanes[1], 'полоса', 'полосы', 'полос') + ' по ' + f.perLane[1] + ' вдоль';
    else layout = [f.rows[1] ? f.rows[1] + ' ' + plural(f.rows[1], 'ряд', 'ряда', 'рядов') + ' вдоль по ' + f.perRow[1] : '', f.rows[0] ? f.rows[0] + ' ' + plural(f.rows[0], 'ряд', 'ряда', 'рядов') + ' поперёк по ' + f.perRow[0] : ''].filter(Boolean).join(' + ');
    const tight = L - f.used < 0.05;
    more.innerHTML = 'Расстановка на полу: ' + (layout || '—') + '. Занято ' + fmt(f.used || 0) + ' из ' + fmt(L) + ' м длины.' + (tight ? ' Паллеты встают почти без зазора — на практике может войти на 1–2 меньше.' : '') +
      (isFinite(kg) && kg > 0 ? ' По массе: ' + (isFinite(t.byMass) ? pal(t.byMass) : '—') + ' при ' + fmt(kg) + ' кг и грузоподъёмности ' + fmt(payload) + ' т; масса груза — ' + fmt(t.total * kg / 1000) + ' т.' : '') +
      ' Распределение по осям проверьте в <a href="/tools/raspredelenie-gruza-po-osyam/">калькуляторе распределения груза</a>.';
    const Wpx = 720, k = (Wpx - 40) / L, h = W * k; let g = '<rect x="20" y="10" width="'+(L*k)+'" height="'+h+'" fill="none" stroke="var(--ink)" stroke-width="2"/>';
    const box = (x, y, w, hh) => g += '<rect x="'+(20+x*k+2)+'" y="'+(10+y*k+2)+'" width="'+(w*k-4)+'" height="'+(hh*k-4)+'" rx="3" fill="#ff6b00" opacity=".75"/>';
    if (f.mode === 'lanes'){
      let y = 0;
      for (let n = 0; n < f.lanes[0]; n++){ for (let i = 0; i < f.perLane[0]; i++) box(i*f.short, y, f.short, f.long); y += f.long; }
      for (let n = 0; n < f.lanes[1]; n++){ for (let i = 0; i < f.perLane[1]; i++) box(i*f.long, y, f.long, f.short); y += f.short; }
    } else {
      let x = 0;
      for (let r = 0; r < f.rows[1]; r++){ for (let c = 0; c < f.perRow[1]; c++) box(x, c*f.short, f.long, f.short); x += f.long; }
      for (let r = 0; r < f.rows[0]; r++){ for (let c = 0; c < f.perRow[0]; c++) box(x, c*f.long, f.short, f.long); x += f.short; }
    }
    svg.setAttribute('viewBox', '0 0 ' + Wpx + ' ' + (h + 20)); svg.innerHTML = g;
  }
  $('#p-body').addEventListener('change', setBody); $('#p-type').addEventListener('change', setPallet);
  document.querySelectorAll('#pallet-form input').forEach(el => el.addEventListener('input', calc));
  setPallet(); setBody();
})();
"""


def render_pallet_calculator_page(base_url: str, telegram_cta: str) -> str:
    canonical = base_url + PAGE_PATH
    title = "Сколько паллет в фуру: калькулятор загрузки еврофуры, рефрижератора и контейнера"
    description = (
        "Калькулятор: сколько европаллет, финских и американских паллет помещается в еврофуру 13,6 м, рефрижератор, контейнер 20 и 40 футов. "
        "Расстановка вдоль и поперёк, ярусы и грузоподъёмность."
    )[:200]
    data = {"bodies": BODIES, "pallets": PALLETS}
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    body_opts = "".join(f'<option value="{b["id"]}">{html.escape(b["name"])}</option>' for b in BODIES) + '<option value="custom">Свои размеры</option>'
    pallet_opts = "".join(f'<option value="{p["id"]}">{html.escape(p["name"])}</option>' for p in PALLETS) + '<option value="custom">Свой размер</option>'
    faq_html = "".join(
        f'<details class="regulation-faq__item"><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>' for q, a in FAQ
    )
    schema = json.dumps(
        [
            {"@context": "https://schema.org", "@type": "WebApplication", "name": "Калькулятор: сколько паллет в фуру",
             "url": canonical, "applicationCategory": "BusinessApplication", "operatingSystem": "Any", "inLanguage": "ru-RU",
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "RUB"}},
            {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ]},
        ],
        ensure_ascii=False, separators=(",", ":"),
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
  <style>{_dist_css()}</style>
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
        <h1>Сколько паллет поместится в фуру</h1>
        <p class="regulation-hero__title">Выберите кузов и тип паллет — калькулятор подберёт расстановку вдоль и поперёк, учтёт ярусы и грузоподъёмность.</p>
      </div>
    </section>

    <section class="container regulation-layout">
      <article class="regulation-main">
        <section class="calc-card" id="pallet-form">
          <p class="section-kicker">Расчёт</p>
          <h2>Кузов и паллеты</h2>
          <div class="calc-row">
            <label class="calc-field">Кузов<select id="p-body">{body_opts}</select></label>
            <label class="calc-field">Паллеты<select id="p-type">{pallet_opts}</select></label>
          </div>
          <div class="dist-grid">
            <label class="calc-field">Длина кузова внутри, м<input id="p-L" inputmode="decimal"></label>
            <label class="calc-field">Ширина кузова внутри, м<input id="p-W" inputmode="decimal"></label>
            <label class="calc-field">Грузоподъёмность, т<input id="p-payload" inputmode="decimal"></label>
            <label class="calc-field">Паллета: длина, м<input id="p-a" inputmode="decimal"></label>
            <label class="calc-field">Паллета: ширина, м<input id="p-b" inputmode="decimal"></label>
            <label class="calc-field">Масса паллеты с грузом, кг<input id="p-kg" inputmode="decimal" value="500"></label>
            <label class="calc-field">Ярусов<input id="p-tiers" inputmode="numeric" value="1"></label>
          </div>
          <svg id="p-scheme" class="dist-scheme" viewBox="0 0 720 140" role="img" aria-label="Схема расстановки паллет на полу кузова"></svg>
          <div class="calc-verdict" id="calc-verdict" aria-live="polite">Заполните данные.</div>
          <p class="calc-note" id="p-more"></p>
          <p class="calc-note">Размеры кузовов типовые — для точного расчёта введите внутренние размеры своего кузова. Второй ярус возможен, только если позволяют высота кузова и прочность груза.</p>
        </section>

        <section class="regulation-section">
          <p class="section-kicker">Шпаргалка</p>
          <h2>Сколько паллет входит в типовые кузова</h2>
          <div class="calc-scroll"><table class="calc-table"><thead><tr><th>Кузов</th><th>EUR 1200×800</th><th>FIN 1200×1000</th></tr></thead><tbody>{_table_rows()}</tbody></table></div>
          <p class="calc-note">Один ярус, без учёта массы. Посчитано тем же калькулятором.</p>
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
            <li><a href="/tools/raspredelenie-gruza-po-osyam/">Калькулятор распределения груза по осям</a></li>
            <li><a href="/knowledge/kreplenie-gruzov/">Крепление грузов в полуприцепе: чек-лист</a></li>
            <li><a href="/knowledge/nagruzka-na-osi-evrofury/">Нагрузка на оси еврофуры</a></li>
            <li><a href="/tools/shtraf-za-peregruz/">Калькулятор штрафа за перегруз</a></li>
          </ul>
        </section>
      </article>

      <aside class="regulation-sidebar">
        <section class="sidebar-block">
          <p class="sidebar-eyebrow">Важно</p>
          <p class="sidebar-text">Калькулятор считает только размещение на полу. Перед погрузкой проверьте нагрузку на оси и закрепите груз.</p>
        </section>
      </aside>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/tools/nagruzka-na-os/">Калькулятор нагрузки</a><a href="{PAGE_PATH}">Сколько паллет в фуру</a><a href="/brands/">Бренды</a><a href="https://t.me/specavtoportal" target="_blank" rel="noopener">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
  <script type="application/json" id="pallet-data">{data_json}</script>
  <script>{_page_js()}</script>
</body>
</html>
"""
