"""Trip cost calculator: /tools/stoimost-reysa/.

Cost of a truck trip: fuel, "Platon" road charge (vehicles over 12 t on
federal roads), toll roads, driver pay and daily allowances, per-km running
costs; cost per kilometre and price with a chosen margin. Driving days are
estimated from the driver rest rules (9 h of driving per day, order No. 160).
Plain JS (TRIP_JS), tested with node.

Platon tariff: 5.19 ₽/km since 01.03.2026 (reported by the trade press,
e.g. spmag.ru and t-j.ru); update PLATON_RATE when it is indexed.
"""
from __future__ import annotations

import html
import json

from load_distribution_calculator import _page_css as _dist_css

PAGE_PATH = "/tools/stoimost-reysa/"
PLATON_RATE = 5.19
PLATON_SINCE = "1 марта 2026 года"

TRIP_JS = r"""
// All money in roubles. Returns the cost breakdown of a trip.
function tripCost(o){
  const km = Math.max(0, o.km || 0);
  const fuelL = km * (o.consumption || 0) / 100;
  const fuel = fuelL * (o.fuelPrice || 0);
  const platon = o.platon ? km * (o.federalShare || 0) / 100 * (o.platonRate || 0) : 0;
  const tolls = o.tolls || 0;
  const driveH = (o.speed || 0) > 0 ? km / o.speed : 0;
  const days = driveH > 0 ? Math.ceil(driveH / (o.dayDrive || 9) - 1e-9) : 0;
  const driver = km * (o.driverPerKm || 0) + days * (o.perDiem || 0);
  const running = km * (o.runningPerKm || 0);
  const cost = fuel + platon + tolls + driver + running;
  const margin = cost * (o.marginPct || 0) / 100;
  return {fuelL, fuel, platon, tolls, days, driver, running, cost, perKm: km > 0 ? cost / km : 0,
          price: cost + margin, pricePerKm: km > 0 ? (cost + margin) / km : 0};
}
"""

FAQ = [
    (
        "Из чего складывается стоимость рейса?",
        "Основные статьи: топливо, плата «Платон» за проезд по федеральным трассам для машин тяжелее 12 т, платные дороги, "
        "оплата водителя и суточные, а также расходы на содержание машины — шины, ТО, ремонт, страховка, лизинг. "
        "Калькулятор складывает их и показывает себестоимость километра и цену с наценкой.",
    ),
    (
        "Сколько стоит «Платон» в 2026 году?",
        f"С {PLATON_SINCE} — {str(PLATON_RATE).replace('.', ',')} ₽ за километр для грузовиков с разрешённой максимальной массой больше 12 т. "
        "Плата начисляется только за километры по федеральным дорогам, поэтому в калькуляторе указывается их доля в маршруте.",
    ),
    (
        "Как посчитать суточные водителя?",
        "Калькулятор оценивает число дней в пути по норме не больше 9 часов за рулём в сутки (приказ Минтранса № 160) и умножает "
        "на размер суточных. Точный график с перерывами и отдыхом можно построить в калькуляторе режима труда и отдыха.",
    ),
    (
        "Что включать в расходы на содержание машины?",
        "Обычно это затраты в рублях на километр: шины, плановое ТО и ремонт, страховка, лизинг или амортизация. "
        "Их удобно посчитать по своему парку за прошлый год: все такие расходы разделить на пробег.",
    ),
]


def _page_js() -> str:
    return TRIP_JS + r"""
(function(){
  const $ = s => document.querySelector(s);
  const num = v => { const x = parseFloat(String(v).replace(',', '.')); return isFinite(x) ? x : 0; };
  const rub = n => Math.round(n).toLocaleString('ru-RU') + ' ₽';
  const ids = ['km','federalShare','consumption','fuelPrice','platonRate','tolls','speed','driverPerKm','perDiem','runningPerKm','marginPct'];
  function calc(){
    const o = {}; ids.forEach(k => o[k] = num($('#t-'+k).value)); o.platon = $('#t-platon').checked; o.dayDrive = 9;
    $('#t-platonRate').closest('label').style.display = $('#t-federalShare').closest('label').style.display = o.platon ? '' : 'none';
    const r = tripCost(o);
    const row = (n, v, hint) => '<tr><td>' + n + (hint ? '<br><small style="color:var(--muted)">' + hint + '</small>' : '') + '</td><td><b>' + rub(v) + '</b></td><td>' + (r.cost > 0 ? Math.round(v / r.cost * 100) + ' %' : '') + '</td></tr>';
    $('#t-result').innerHTML = '<table class="calc-table"><thead><tr><th>Статья</th><th>Сумма</th><th>Доля</th></tr></thead><tbody>' +
      row('Топливо', r.fuel, Math.round(r.fuelL).toLocaleString('ru-RU') + ' л') +
      (o.platon ? row('«Платон»', r.platon, Math.round(o.km * o.federalShare / 100).toLocaleString('ru-RU') + ' км по федеральным трассам') : '') +
      row('Платные дороги', r.tolls) +
      row('Водитель', r.driver, r.days + ' ' + (r.days % 10 === 1 && r.days % 100 !== 11 ? 'день' : (r.days % 10 >= 2 && r.days % 10 <= 4 && (r.days % 100 < 12 || r.days % 100 > 14)) ? 'дня' : 'дней') + ' в пути') +
      row('Содержание машины', r.running) +
      '</tbody></table>';
    $('#calc-verdict').className = 'calc-verdict ok';
    $('#calc-verdict').innerHTML = 'Себестоимость рейса: <b>' + rub(r.cost) + '</b> — ' + (Math.round(r.perKm * 100) / 100).toLocaleString('ru-RU') + ' ₽/км.';
    $('#t-price').innerHTML = 'Цена с наценкой ' + o.marginPct.toLocaleString('ru-RU') + ' %: <b>' + rub(r.price) + '</b> (' + (Math.round(r.pricePerKm * 100) / 100).toLocaleString('ru-RU') + ' ₽/км).';
  }
  document.querySelectorAll('#trip-form input').forEach(el => { el.addEventListener('input', calc); el.addEventListener('change', calc); });
  calc();
})();
"""


def _field(key: str, label: str, value: str) -> str:
    return f'<label class="calc-field">{html.escape(label)}<input id="t-{key}" inputmode="decimal" value="{html.escape(value, quote=True)}"></label>'


def render_trip_cost_page(base_url: str, telegram_cta: str) -> str:
    canonical = base_url + PAGE_PATH
    title = "Калькулятор стоимости рейса грузовика 2026 — топливо, «Платон», водитель"
    description = (
        "Посчитайте себестоимость грузоперевозки: топливо, «Платон» 5,19 ₽/км, платные дороги, оплата и суточные водителя, "
        "содержание машины. Стоимость километра и цена рейса с наценкой."
    )[:200]
    rate = str(PLATON_RATE).replace(".", ",")
    route = "".join(_field(*x) for x in (
        ("km", "Расстояние, км", "1500"),
        ("speed", "Средняя скорость, км/ч", "65"),
        ("tolls", "Платные дороги, ₽", "0"),
    ))
    fuel = "".join(_field(*x) for x in (
        ("consumption", "Расход, л/100 км", "32"),
        ("fuelPrice", "Цена дизеля, ₽/л", "70"),
        ("runningPerKm", "Содержание машины, ₽/км", "15"),
    ))
    platon = "".join(_field(*x) for x in (
        ("federalShare", "Доля федеральных трасс, %", "70"),
        ("platonRate", "Тариф «Платон», ₽/км", rate),
    ))
    driver = "".join(_field(*x) for x in (
        ("driverPerKm", "Оплата водителя, ₽/км", "12"),
        ("perDiem", "Суточные, ₽/день", "1000"),
        ("marginPct", "Наценка, %", "15"),
    ))
    faq_html = "".join(
        f'<details class="regulation-faq__item"><summary>{html.escape(q)}</summary><p>{html.escape(a)}</p></details>' for q, a in FAQ
    )
    schema = json.dumps(
        [
            {"@context": "https://schema.org", "@type": "WebApplication", "name": "Калькулятор стоимости рейса грузовика",
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
        <h1>Калькулятор стоимости рейса</h1>
        <p class="regulation-hero__title">Себестоимость грузоперевозки по статьям: топливо, «Платон», платные дороги, водитель и содержание машины — и цена рейса с наценкой.</p>
      </div>
    </section>

    <section class="container regulation-layout">
      <article class="regulation-main">
        <section class="calc-card" id="trip-form">
          <p class="section-kicker">Расчёт</p>
          <h2>Маршрут и затраты</h2>
          <p class="dist-sub">Маршрут</p>
          <div class="dist-grid">{route}</div>
          <p class="dist-sub">Машина</p>
          <div class="dist-grid">{fuel}</div>
          <label class="calc-check"><input type="checkbox" id="t-platon" checked> Машина тяжелее 12 т — платить «Платон»</label>
          <div class="dist-grid">{platon}</div>
          <p class="dist-sub">Водитель и наценка</p>
          <div class="dist-grid">{driver}</div>
          <div id="t-result" class="calc-scroll" style="margin-top:16px"></div>
          <div class="calc-verdict" id="calc-verdict" aria-live="polite">Заполните данные.</div>
          <div class="dist-range" id="t-price"></div>
          <p class="calc-note">Значения по умолчанию — пример для магистрального тягача, замените их своими. Цена топлива меняется — подставьте актуальную. Дни в пути оцениваются по норме 9 часов за рулём в сутки; подробный график — в <a href="/tools/rezhim-truda-i-otdyha/">калькуляторе режима труда и отдыха</a>.</p>
        </section>

        <section class="regulation-section">
          <p class="section-kicker">Справка</p>
          <h2>«Платон» в 2026 году</h2>
          <p>С {PLATON_SINCE} плата в системе «Платон» — {rate} ₽ за километр. Её вносят владельцы грузовиков с разрешённой максимальной массой больше 12 т за проезд по федеральным дорогам. Региональные и местные дороги в расчёт не входят, поэтому в калькуляторе указывается доля федеральных трасс в маршруте. Подробнее — в статье <a href="/knowledge/platon-2026/">«„Платон“ в 2026 году»</a>.</p>
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
            <li><a href="/knowledge/platon-2026/">«Платон» в 2026 году: тариф, кто платит, штрафы</a></li>
            <li><a href="/tools/rezhim-truda-i-otdyha/">Режим труда и отдыха водителя</a></li>
            <li><a href="/tools/skolko-pallet-v-furu/">Сколько паллет в фуру</a></li>
            <li><a href="/tools/raspredelenie-gruza-po-osyam/">Распределение груза по осям</a></li>
            <li><a href="/tools/shtraf-za-peregruz/">Штраф за перегруз</a></li>
          </ul>
        </section>
      </article>

      <aside class="regulation-sidebar">
        <section class="sidebar-block">
          <p class="sidebar-eyebrow">Важно</p>
          <p class="sidebar-text">Расчёт ориентировочный. Он не учитывает простои, порожний пробег, налоги и стоимость денег — добавьте их в наценку или в содержание машины.</p>
        </section>
      </aside>
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/tools/nagruzka-na-os/">Калькулятор нагрузки</a><a href="{PAGE_PATH}">Стоимость рейса</a><a href="/brands/">Бренды</a><a href="https://t.me/specavtoportal" target="_blank" rel="noopener">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
  <script>{_page_js()}</script>
</body>
</html>
"""
