"""Hub page with all free calculators: /tools/."""
from __future__ import annotations

import html
import json

PAGE_PATH = "/tools/"

# (path, title, what it does, typical question it answers)
TOOLS = [
    ("/tools/nagruzka-na-os/", "Нагрузка на ось", "Проверка нагрузок на одиночные, сдвоенные и строенные оси и общей массы по ПП № 2060 для дорог 6, 10 и 11,5 т/ось.", "Не перегружена ли ось?"),
    ("/tools/raspredelenie-gruza-po-osyam/", "Распределение груза по осям", "Масса и положение груза → нагрузка на оси тягача, полуприцепа или грузовика с КМУ; зона, где ставить груз без перегруза.", "Куда поставить груз?"),
    ("/tools/shtraf-za-peregruz/", "Штраф за перегруз", "Процент превышения массы, нагрузки на ось или габаритов и сумма штрафа собственнику по статье 12.21.1 КоАП.", "Сколько будет штраф?"),
    ("/tools/skolko-pallet-v-furu/", "Сколько паллет в фуру", "Европаллеты, финские и американские паллеты в еврофуре, рефрижераторе и контейнере: расстановка, ярусы, грузоподъёмность.", "Сколько войдёт паллет?"),
    ("/tools/stoimost-reysa/", "Стоимость рейса", "Топливо, «Платон», платные дороги, водитель и содержание машины — себестоимость километра и цена с наценкой.", "Во сколько обойдётся рейс?"),
    ("/tools/rashod-topliva/", "Расход топлива", "Литры и деньги на рейс с учётом массы груза, порожнего пробега и зимней надбавки; запас хода и заправки в пути.", "Сколько топлива нужно на рейс?"),
    ("/tools/rezhim-truda-i-otdyha/", "Режим труда и отдыха", "График рейса по приказу Минтранса № 160: перерывы по 45 минут, ежедневный и еженедельный отдых, время прибытия.", "Когда приедет водитель?"),
]


def render_tools_hub(base_url: str, telegram_cta: str) -> str:
    canonical = base_url + PAGE_PATH
    title = "Калькуляторы для перевозчиков — нагрузка на ось, штрафы, паллеты, стоимость рейса"
    description = (
        "Бесплатные онлайн-калькуляторы для грузоперевозок: нагрузка на ось и распределение груза, штраф за перегруз, "
        "сколько паллет в фуру, стоимость рейса и режим труда и отдыха водителя."
    )[:200]
    cards = "".join(
        f'<a class="knowledge-section-card" href="{href}">'
        f'<span class="knowledge-section-card__eyebrow">{html.escape(q)}</span>'
        f"<h2>{html.escape(name)}</h2><p>{html.escape(text)}</p>"
        '<span class="knowledge-section-card__link">Открыть калькулятор →</span></a>'
        for href, name, text, q in TOOLS
    )
    schema = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "ItemList",
            "name": "Калькуляторы для перевозчиков",
            "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "url": base_url + href, "name": name}
                for i, (href, name, _t, _q) in enumerate(TOOLS)
            ],
        },
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
  <link rel="stylesheet" href="/styles.css?v=31" />
  <link rel="icon" href="/spec_avtoportal_favicon.ico" type="image/x-icon" />
  <script type="application/ld+json">{schema}</script>
</head>
<body class="knowledge-page">
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
        <h1>Калькуляторы для перевозчиков</h1>
        <p class="regulation-hero__title">Бесплатно, без регистрации, работают с телефона. Нормы — по действующим постановлениям и КоАП 2026 года.</p>
      </div>
    </section>
    <section class="container knowledge-sections" style="margin-top:24px">
      {cards}
    </section>
    <section class="container" style="margin:28px auto">
      {telegram_cta}
    </section>
  </main>

  <footer class="site-footer">
    <div class="container footer-grid">
      <div><a href="/" class="footer-brand">СпецАвтоПортал</a><p>Отраслевое медиа о прицепах, полуприцепах и грузовой технике.</p></div>
      <div class="footer-nav"><a href="/knowledge.html">База знаний</a><a href="/law.html">Нормативы</a><a href="/tools/">Калькуляторы</a><a href="/brands/">Бренды</a><a href="https://t.me/specavtoportal" target="_blank" rel="noopener">Telegram ↗</a></div>
      <div class="footer-note">© СпецАвтоПортал</div>
    </div>
  </footer>
</body>
</html>
"""
