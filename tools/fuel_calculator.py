"""Fuel consumption calculator: /tools/rashod-topliva/.

Fuel for a truck trip from the owner's own consumption figures: empty and at
full payload, interpolated linearly by the actual cargo mass, with loaded and
empty kilometres counted separately, a winter surcharge, fuel cost, average
l/100 km and refuelling stops for a given tank. Plain JS (FUEL_JS), tested with
node. The page also explains the accounting norm formula of the Ministry of
Transport recommendations No. AM-23-r (Hw = 1.3 l per 100 t*km for diesel,
2.0 for petrol).
"""
from __future__ import annotations

import html
import json

from load_distribution_calculator import _page_css as _dist_css

PAGE_PATH = "/tools/rashod-topliva/"

FUEL_JS = r"""
// Litres and roubles for a trip. cargo/payload shifts the loaded consumption
// between the empty and the full-load figure (linear, capped at 150 % load).
function fuelTrip(o){
  const km = Math.max(0, o.km || 0);
  const loadedKm = Math.min(km, Math.max(0, o.loadedKm || 0));
  const emptyKm = km - loadedKm;
  const emptyL = Math.max(0, o.emptyL || 0);
  const fullL = Math.max(0, o.fullL || 0);
  const share = (o.payload || 0) > 0 ? Math.min(1.5, Math.max(0, (o.cargo || 0) / o.payload)) : 0;
  const loadedRate = emptyL + (fullL - emptyL) * share;
  const base = (loadedKm * loadedRate + emptyKm * emptyL) / 100;
  const litres = base * (1 + (o.winterPct || 0) / 100);
  const cost = litres * (o.price || 0);
  const per100 = km > 0 ? litres / km * 100 : 0;
  const usable = (o.tank || 0) * 0.9;            // keep a 10 % reserve in the tank
  const range = per100 > 0 ? usable / per100 * 100 : 0;
  const stops = usable > 0 ? Math.max(0, Math.ceil(litres / usable - 1e-9) - 1) : 0;
  return {loadedRate, litres, cost, per100, perKm: km > 0 ? cost / km : 0, range, stops, share};
}
"""

FAQ = [
    (
        "Как посчитать расход топлива фуры на рейс?",
        "Нужны два своих значения: расход порожней машины и расход с полной загрузкой, в литрах на 100 км. Калькулятор "
        "подставляет промежуточный расход для фактической массы груза, отдельно считает километры с грузом и порожние, "
        "добавляет зимнюю надбавку и показывает литры, стоимость и сколько раз придётся заправиться.",
    ),
    (
        "Насколько груз увеличивает расход?",
        "Зависит от машины, дороги и скорости. Удобнее всего взять свои цифры: расход порожняком и с полной загрузкой по "
        "данным бортового компьютера или топливных карт. В нормах Минтранса (распоряжение № АМ-23-р) для дизельных машин "
        "закладывается 1,3 л на каждые 100 тонно-километров транспортной работы, для бензиновых — 2 л.",
    ),
    (
        "Какая зимняя надбавка к расходу топлива?",
        "По распоряжению Минтранса № АМ-23-р зимняя надбавка устанавливается от 5 до 20 % в зависимости от климатического "
        "района. Конкретные значения и сроки зимнего периода для регионов приведены в приложении к распоряжению.",
    ),
    (
        "Чем норма расхода отличается от фактического расхода?",
        "Норма по АМ-23-р нужна для учёта и списания топлива в бухгалтерии, её считают по формуле от базовой нормы машины. "
        "Фактический расход зависит от конкретной машины, водителя, маршрута и погоды — для планирования рейса удобнее "
        "считать от своего реального расхода.",
    ),
]


def _page_js() -> str:
    return FUEL_JS + r"""
(function(){
  const $ = s => document.querySelector(s);
  const num = v => { const x = parseFloat(String(v).replace(',', '.')); return isFinite(x) ? x : 0; };
  const fmt = (n, d) => (Math.round(n * Math.pow(10, d || 0)) / Math.pow(10, d || 0)).toLocaleString('ru-RU');
  const ids = ['km','loadedKm','emptyL','fullL','payload','cargo','winterPct','price','tank'];
  function plural(n, a, b, c){ const m = n % 10, h = n % 100; return m === 1 && h !== 11 ? a : (m >= 2 && m <= 4 && (h < 12 || h > 14)) ? b : c; }
  function calc(){
    const o = {}; ids.forEach(k => o[k] = num($('#f-'+k).value));
    const r = fuelTrip(o);
    const row = (n, v) => '<tr><td>' + n + '</td><td><b>' + v + '</b></td></tr>';
    $('#f-result').innerHTML = '<table class="calc-table"><tbody>' +
      row('Расход с этим грузом', fmt(r.loadedRate, 1) + ' л/100 км') +
      row('Средний расход за рейс', fmt(r.per100, 1) + ' л/100 км') +
      row('Топлива на рейс', fmt(r.litres) + ' л') +
      row('Стоимость топлива', fmt(r.cost) + ' ₽') +
      row('Топливо на 1 км', fmt(r.perKm, 2) + ' ₽') +
      (o.tank > 0 ? row('Запас хода на баке', fmt(r.range) + ' км') : '') +
      '</tbody></table>';
    $('#calc-verdict').className = 'calc-verdict ok';
    $('#calc-verdict').innerHTML = 'На рейс нужно около <b>' + fmt(r.litres) + ' л</b> топлива — <b>' + fmt(r.cost) + ' ₽</b>.' +
      (o.tank > 0 ? ' С полным баком в начале: ' + (r.stops === 0 ? 'без заправок в пути.' : r.stops + ' ' + plural(r.stops, 'заправка', 'заправки', 'заправок') + ' в пути.') : '');
    $('#f-warn').textContent = (o.loadedKm > o.km) ? 'Пробег с грузом больше общего — считаю весь путь с грузом.' :
      (o.payload > 0 && o.cargo > o.payload) ? 'Груз больше полной загрузки — проверьте массу и нагрузки на оси.' : '';
  }
  document.querySelectorAll('#fuel-form input').forEach(el => { el.addEventListener('input', calc); el.addEventListener('change', calc); });
  calc();
})();
"""


def _field(key: str, label: str, value: str) -> str:
    return f'<label class="calc-field">{html.escape(label)}<input id="f-{key}" inputmode="decimal" value="{html.escape(value, quote=True)}"></label>'


def render_fuel_calculator_page(base_url: str, telegram_cta: str) -> str:
    canonical = base_url + PAGE_PATH
    title = "Калькулятор расхода топлива грузовика и фуры на рейс 2026"
    description = (
        "Сколько топлива нужно фуре на рейс: расход с грузом и порожняком, зимняя надбавка, стоимость топлива, "
        "запас хода и число заправок. Формула нормы расхода по АМ-23-р."
    )[:200]
    route = "".join(_field(*x) for x in (
        ("km", "Пробег за рейс, км", "1500"),
        ("loadedKm", "Из них с грузом, км", "1500"),
        ("winterPct", "Зимняя надбавка, %", "0"),
    ))
    truck = "".join(_field(*x) for x in (
        ("emptyL", "Расход порожняком, л/100 км", "26"),
        ("fullL", "Расход с полной загрузкой, л/100 км", "34"),
        ("payload", "Полная загрузка, т", "20"),
        ("cargo", "Масса груза в рейсе, т", "16"),
    ))
    money = "".join(_field(*x) for x in (
        ("price", "Цена дизеля, ₽/л", "70"),
        ("tank", "Объём бака, л", "600"),
    ))
    faq_html = "".join(
        f'<details class="regulation-faq__item"><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>' for q, a in FAQ
    )
    schema = json.dumps(
        [
            {"@context": "https://schema.org", "@type": "WebApplication", "name": "Калькулятор расхода топлива грузовика",
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
  <link rel="stylesheet" href="/styles.css?v=31" />
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
        <p class="section-kicker"><a href="/tools/">Калькуляторы</a> · Инструменты</p>
        <h1>Калькулятор расхода топлива грузовика</h1>
        <p class="regulation-hero__title">Сколько топлива нужно фуре на рейс с учётом массы груза, порожнего пробега и зимы — литры, деньги, запас хода и заправки в пути.</p>
      </div>
    </section>

    <section class="container regulation-layout">
      <article class="regulation-main">
        <section class="calc-card" id="fuel-form">
          <p class="section-kicker">Расчёт</p>
          <h2>Рейс и машина</h2>
          <p class="dist-sub">Рейс</p>
          <div class="dist-grid">{route}</div>
          <p class="dist-sub">Расход вашей машины</p>
          <div class="dist-grid">{truck}</div>
          <p class="dist-sub">Топливо</p>
          <div class="dist-grid">{money}</div>
          <div id="f-result" class="calc-scroll" style="margin-top:16px"></div>
          <div class="calc-verdict" id="calc-verdict" aria-live="polite">Заполните данные.</div>
          <div class="dist-range" id="f-warn"></div>
          <p class="calc-note">Расход порожняком и с полной загрузкой возьмите из бортового компьютера или топливных карт своей машины — значения по умолчанию только пример. Для промежуточной загрузки расход считается пропорционально массе груза. В запасе хода оставлено 10 % бака на резерв.</p>
        </section>

        <section class="regulation-section">
          <p class="section-kicker">Справка</p>
          <h2>Норма расхода топлива по АМ-23-р</h2>
          <p>Для учёта и списания топлива организации используют методические рекомендации Минтранса — распоряжение № АМ-23-р от 14.03.2008. Для грузовика или тягача с прицепом норма считается так:</p>
          <p><b>Qн = 0,01 × (Hsan × S + Hw × W) × (1 + 0,01 × D)</b>, где <b>Hsan = Hs + Hg × Gпр</b>.</p>
          <ul>
            <li><b>Qн</b> — нормативный расход, л; <b>S</b> — пробег, км;</li>
            <li><b>Hs</b> — базовая норма машины без груза, л/100 км (из распоряжения или письма производителя);</li>
            <li><b>Hg</b> — норма на массу прицепа или полуприцепа, <b>Gпр</b> — его собственная масса, т;</li>
            <li><b>Hw</b> — норма на транспортную работу: 1,3 л на 100 т·км для дизеля, 2 л — для бензина; <b>W</b> — масса груза × пробег с грузом, т·км;</li>
            <li><b>D</b> — надбавки в процентах: зимняя — от 5 до 20 %, работа в городе, горная местность и другие.</li>
          </ul>
          <p>Норма нужна бухгалтерии. Для планирования рейса удобнее считать от фактического расхода своей машины — как в калькуляторе выше. Полную стоимость рейса с «Платоном», водителем и платными дорогами посчитает <a href="/tools/stoimost-reysa/">калькулятор стоимости рейса</a>.</p>
        </section>

        {telegram_cta}

        <section class="regulation-section regulation-faq">
          <p class="section-kicker">Вопросы и ответы</p>
          <h2>Частые вопросы</h2>
          {faq_html}
        </section>

        <section class="regulation-section">
          <p class="section-kicker">По теме</p>
          <h2>Другие калькуляторы</h2>
          <ul>
            <li><a href="/tools/stoimost-reysa/">Стоимость рейса: топливо, «Платон», водитель</a></li>
            <li><a href="/knowledge/platon-2026/">«Платон» в 2026 году: тариф, кто платит, штрафы</a></li>
            <li><a href="/tools/raspredelenie-gruza-po-osyam/">Распределение груза по осям</a></li>
            <li><a href="/tools/rezhim-truda-i-otdyha/">Режим труда и отдыха водителя</a></li>
          </ul>
        </section>
      </article>

      <aside class="regulation-sidebar">
        <section class="sidebar-block">
          <p class="sidebar-eyebrow">Важно</p>
          <p class="sidebar-text">Расчёт ориентировочный: расход сильно зависит от скорости, рельефа, ветра, шин и манеры езды. Сравнивайте результат с фактом по топливным картам и уточняйте свои цифры.</p>
        </section>
      </aside>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/tools/">Калькуляторы</a><a href="{PAGE_PATH}">Расход топлива</a><a href="/brands/">Бренды</a><a href="https://t.me/specavtoportal" target="_blank" rel="noopener">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
  <script>{_page_js()}</script>
</body>
</html>
"""
