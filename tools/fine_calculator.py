"""Overload fine calculator: /tools/shtraf-za-peregruz/.

Fines for the owner (владелец) of a vehicle under article 12.21.1 of the
Code of Administrative Offences, as amended by Federal Law No. 209-FZ
(in force since 18.07.2025), for driving without a special permit:

  dimensions: up to 10 cm — part 1, 150 000 ₽ (not imposed from cameras);
              over 10 up to 20 cm — part 4, 300 000 ₽;
              over 20 up to 50 cm — part 5, 450 000 ₽; over 50 cm — part 6, 600 000 ₽.
  mass / axle load: over 10 up to 20 % — part 4, 300 000 ₽;
              over 20 up to 50 % — part 5, 450 000 ₽; over 50 % — part 6, 600 000 ₽.
              Up to 10 % — no separate part of the article.

The percentage is counted from the permissible value. The logic is plain JS
(FINE_JS) so it is tested with node and runs in the browser.
"""
from __future__ import annotations

import html
import json

from axle_calculator import MASS_LIMITS
from load_distribution_calculator import _page_css as _dist_css

PAGE_PATH = "/tools/shtraf-za-peregruz/"
LAW_URL = "https://www.consultant.ru/document/cons_doc_LAW_34661/f727c535f35518ba16c7d51b782a5f6ed67b76a3/"

# Appendix 1 to Government Decree No. 2060.
DIMENSIONS = {"length": 20, "length_single": 12, "width": 2.6, "height": 4}

FINE_JS = r"""
// kind: 'mass' | 'axle' (percent of the permissible value) or 'dim' (centimetres).
function overloadFine(kind, allowed, actual){
  const eps = 1e-9;
  if (!(allowed > 0) || !(actual >= 0)) return null;
  if (kind === 'dim'){
    const cm = Math.round((actual - allowed) * 100 * 1000) / 1000;
    if (cm <= eps) return {over: false, cm, part: null, fine: 0};
    if (cm <= 10 + eps) return {over: true, cm, part: 1, fine: 150000, cameraExempt: true};
    if (cm <= 20 + eps) return {over: true, cm, part: 4, fine: 300000};
    if (cm <= 50 + eps) return {over: true, cm, part: 5, fine: 450000};
    return {over: true, cm, part: 6, fine: 600000};
  }
  const pct = Math.round((actual - allowed) / allowed * 100 * 1000) / 1000;
  if (pct <= eps) return {over: false, pct, part: null, fine: 0};
  if (pct <= 10 + eps) return {over: true, pct, part: null, fine: 0, belowThreshold: true};
  if (pct <= 20 + eps) return {over: true, pct, part: 4, fine: 300000};
  if (pct <= 50 + eps) return {over: true, pct, part: 5, fine: 450000};
  return {over: true, pct, part: 6, fine: 600000};
}

// Largest actual value that still stays without a fine (up to +10 % for mass and axle load).
function maxWithoutFine(kind, allowed){
  return kind === 'dim' ? allowed : allowed * 1.1;
}
"""

FAQ = [
    (
        "С какого перегруза начинается штраф?",
        "По массе и нагрузке на ось — с превышения более чем на 10 % от допустимого значения: от 10 до 20 % — 300 000 ₽, "
        "от 20 до 50 % — 450 000 ₽, больше 50 % — 600 000 ₽. Отдельной части статьи 12.21.1 о превышении до 10 % нет.",
    ),
    (
        "Кто платит штраф за перегруз?",
        "По частям 1, 4, 5 и 6 статьи 12.21.1 КоАП — собственник (владелец) транспортного средства. Сумма фиксированная и одинаковая "
        "для организации, ИП и гражданина.",
    ),
    (
        "Как считается процент перегруза?",
        "От допустимого значения: для массы автопоезда — от предельной массы для его числа осей, для нагрузки на ось — от допустимой "
        "нагрузки на ось или группу осей для дороги. Например, 49 т при пределе 44 т — это превышение на 11,4 %.",
    ),
    (
        "А если превышены габариты?",
        "Превышение габаритов до 10 см — 150 000 ₽ (по камерам этот штраф не назначают), от 10 до 20 см — 300 000 ₽, "
        "от 20 до 50 см — 450 000 ₽, больше 50 см — 600 000 ₽.",
    ),
]


def _page_js() -> str:
    return FINE_JS + r"""
(function(){
  const D = JSON.parse(document.getElementById('fine-data').textContent);
  const $ = s => document.querySelector(s);
  const num = v => { const x = parseFloat(String(v).replace(',', '.')); return isFinite(x) ? x : NaN; };
  const fmt = n => (Math.round(n*100)/100).toLocaleString('ru-RU');
  const money = n => n.toLocaleString('ru-RU') + ' ₽';
  function massLimit(kind, axles){
    const t = D.mass[kind]; const keys = Object.keys(t).map(Number).sort((a,b) => a-b);
    if (axles < keys[0]) return NaN; return t[keys.filter(k => k <= axles).pop()];
  }
  function sync(){
    const kind = $('#f-kind').value;
    document.querySelectorAll('[data-for]').forEach(e => e.style.display = e.dataset.for.split(' ').includes(kind) ? '' : 'none');
    if (kind === 'mass' && $('#f-auto').checked){
      const v = massLimit($('#f-vehicle').value, Math.round(num($('#f-axles').value)));
      $('#f-allowed').value = isFinite(v) ? String(v).replace('.', ',') : '';
    }
    if (kind === 'dim' && $('#f-auto-dim').checked){ $('#f-allowed').value = String(D.dims[$('#f-dim').value]).replace('.', ','); }
    $('#f-allowed').readOnly = (kind === 'mass' && $('#f-auto').checked) || (kind === 'dim' && $('#f-auto-dim').checked);
    $('#unit-a').textContent = $('#unit-b').textContent = kind === 'dim' ? 'м' : 'т';
    calc();
  }
  function calc(){
    const kind = $('#f-kind').value, allowed = num($('#f-allowed').value), actual = num($('#f-actual').value);
    const out = $('#calc-verdict'), more = $('#fine-more');
    const r = overloadFine(kind, allowed, actual);
    if (!r) { out.className = 'calc-verdict'; out.textContent = 'Укажите допустимое и фактическое значение.'; more.innerHTML = ''; return; }
    const unit = kind === 'dim' ? 'м' : 'т';
    const size = kind === 'dim' ? fmt(r.cm) + ' см' : fmt(actual - allowed) + ' т (' + fmt(r.pct) + ' %)';
    if (!r.over) { out.className = 'calc-verdict ok'; out.textContent = 'Превышения нет: запас ' + fmt(allowed - actual) + ' ' + unit + '.'; }
    else if (!r.part) { out.className = 'calc-verdict'; out.textContent = 'Превышение ' + size + ' — не больше 10 %: штрафы по частям 4–6 статьи 12.21.1 начинаются с превышения больше 10 %. Но ехать так без спецразрешения всё равно нельзя — транспортное средство считается тяжеловесным.'; }
    else { out.className = 'calc-verdict bad'; out.textContent = 'Превышение ' + size + ' — часть ' + r.part + ' статьи 12.21.1 КоАП: штраф собственнику ' + money(r.fine) + '.'; }
    const lim = maxWithoutFine(kind, allowed);
    more.innerHTML = (kind === 'dim'
      ? 'Допустимо: ' + fmt(allowed) + ' м.'
      : 'Допустимо: ' + fmt(allowed) + ' т. Штраф 300 000 ₽ и выше — при значении больше ' + fmt(lim) + ' т (превышение больше 10 %).')
      + (r.cameraExempt ? ' Штраф по части 1 не назначают, если превышение зафиксировано камерами автоматического контроля.' : '')
      + (r.over && kind !== 'dim' ? ' Проверить, как перераспределить груз по осям, можно в <a href="/tools/raspredelenie-gruza-po-osyam/">калькуляторе распределения груза</a>.' : '');
  }
  document.querySelectorAll('#fine-form input, #fine-form select').forEach(el => { el.addEventListener('input', sync); el.addEventListener('change', sync); });
  sync();
})();
"""


def render_fine_calculator_page(base_url: str, telegram_cta: str) -> str:
    canonical = base_url + PAGE_PATH
    title = "Калькулятор штрафа за перегруз 2026 — по статье 12.21.1 КоАП"
    description = (
        "Посчитайте штраф за перегруз грузовика, превышение нагрузки на ось или габаритов: процент превышения и сумма по статье 12.21.1 КоАП "
        "в редакции 2025 года — 150, 300, 450 или 600 тысяч рублей собственнику."
    )[:200]
    data = {"mass": {k: {str(n): v for n, v in t.items()} for k, t in MASS_LIMITS.items()}, "dims": DIMENSIONS}
    data_json = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    faq_html = "".join(
        f'<details class="regulation-faq__item"><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>' for q, a in FAQ
    )
    schema = json.dumps(
        [
            {"@context": "https://schema.org", "@type": "WebApplication", "name": "Калькулятор штрафа за перегруз",
             "url": canonical, "applicationCategory": "BusinessApplication", "operatingSystem": "Any", "inLanguage": "ru-RU",
             "offers": {"@type": "Offer", "price": "0", "priceCurrency": "RUB"}},
            {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
                {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in FAQ]},
        ],
        ensure_ascii=False, separators=(",", ":"),
    ).replace("</", "<\\/")
    table = "".join(
        f"<tr><td>{html.escape(a)}</td><td>{html.escape(b)}</td><td>{html.escape(c)}</td></tr>" for a, b, c in (
            ("ч. 1", "до 10 см", "150 000 ₽ (не по камерам)"),
            ("ч. 4", "более 10 до 20 % или более 10 до 20 см", "300 000 ₽"),
            ("ч. 5", "более 20 до 50 % или более 20 до 50 см", "450 000 ₽"),
            ("ч. 6", "более 50 % или более 50 см", "600 000 ₽"),
        )
    )
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
  <link rel="stylesheet" href="/styles.css?v=29" />
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
        <h1>Калькулятор штрафа за перегруз</h1>
        <p class="regulation-hero__title">Введите допустимое и фактическое значение — калькулятор посчитает процент превышения и штраф по статье 12.21.1 КоАП.</p>
      </div>
    </section>

    <section class="container regulation-layout">
      <article class="regulation-main">
        <section class="calc-card" id="fine-form">
          <p class="section-kicker">Расчёт</p>
          <h2>Что превышено</h2>
          <div class="calc-row">
            <label class="calc-field">Параметр
              <select id="f-kind"><option value="mass">Масса автомобиля или автопоезда</option><option value="axle">Нагрузка на ось или группу осей</option><option value="dim">Габарит: длина, ширина, высота</option></select></label>
          </div>
          <div class="calc-row" data-for="mass" style="margin-top:12px">
            <label class="calc-field">Транспортное средство
              <select id="f-vehicle"><option value="train">Автопоезд</option><option value="truck">Одиночный автомобиль</option></select></label>
            <label class="calc-field">Число осей<input id="f-axles" inputmode="numeric" value="5"></label>
          </div>
          <label class="calc-check" data-for="mass"><input type="checkbox" id="f-auto" checked> Взять допустимую массу из ПП № 2060 по числу осей</label>
          <div class="calc-row" data-for="dim" style="margin-top:12px">
            <label class="calc-field">Габарит
              <select id="f-dim"><option value="height">Высота (4 м)</option><option value="width">Ширина (2,6 м)</option><option value="length">Длина автопоезда (20 м)</option><option value="length_single">Длина одиночного ТС или прицепа (12 м)</option></select></label>
          </div>
          <label class="calc-check" data-for="dim"><input type="checkbox" id="f-auto-dim" checked> Взять общий допустимый габарит</label>
          <p class="calc-note" data-for="axle">Допустимую нагрузку на ось или группу осей для вашей дороги и расстояния между осями посмотрите в <a href="/tools/nagruzka-na-os/">калькуляторе нагрузки на ось</a>.</p>
          <div class="calc-row" style="margin-top:12px">
            <label class="calc-field">Допустимо, <span id="unit-a">т</span><input id="f-allowed" inputmode="decimal" value="10"></label>
            <label class="calc-field">Фактически, <span id="unit-b">т</span><input id="f-actual" inputmode="decimal" value="46"></label>
          </div>
          <div class="calc-verdict" id="calc-verdict" aria-live="polite">Заполните данные.</div>
          <p class="calc-note" id="fine-more"></p>
        </section>

        <section class="regulation-section">
          <p class="section-kicker">Нормы</p>
          <h2>Штрафы собственнику по статье 12.21.1 КоАП</h2>
          <div class="calc-scroll"><table class="calc-table"><thead><tr><th>Часть</th><th>Превышение без спецразрешения</th><th>Штраф</th></tr></thead><tbody>{table}</tbody></table></div>
          <p class="calc-note">Редакция Федерального закона № 209-ФЗ, действует с 18 июля 2025 года. Процент считается от допустимого значения или от значения в специальном разрешении. Подробный разбор — в статье <a href="/knowledge/shtraf-za-peregruz/">«Штраф за перегруз грузовика в 2026 году»</a>.</p>
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
            <li><a href="/tools/nagruzka-na-os/">Калькулятор нагрузки на ось</a></li>
            <li><a href="/tools/raspredelenie-gruza-po-osyam/">Калькулятор распределения груза по осям</a></li>
            <li><a href="/knowledge/shtraf-za-peregruz/">Штраф за перегруз: все части статьи 12.21.1</a></li>
            <li><a href="/knowledge/specrazreshenie-tyazhelovesnoe-ts/">Спецразрешение на тяжеловесный транспорт</a></li>
          </ul>
        </section>
      </article>

      <aside class="regulation-sidebar">
        <section class="sidebar-block sidebar-dark">
          <p class="sidebar-eyebrow">Первоисточник</p>
          <h3>Статья 12.21.1 КоАП РФ</h3>
          <p class="sidebar-text">Нарушение правил движения тяжеловесного и (или) крупногабаритного транспортного средства.</p>
          <a class="partner-card__button" href="{LAW_URL}" target="_blank" rel="noopener">Открыть текст статьи <span>↗</span></a>
        </section>
        <section class="sidebar-block">
          <p class="sidebar-eyebrow">Важно</p>
          <p class="sidebar-text">Калькулятор справочный. Итоговое решение принимает орган, рассматривающий дело, по данным весового и габаритного контроля.</p>
        </section>
      </aside>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/law.html">Нормативы</a><a href="/tools/nagruzka-na-os/">Калькулятор нагрузки</a><a href="{PAGE_PATH}">Штраф за перегруз</a><a href="/brands/">Бренды</a><a href="https://t.me/specavtoportal" target="_blank" rel="noopener">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
  <script type="application/json" id="fine-data">{data_json}</script>
  <script>{_page_js()}</script>
</body>
</html>
"""
