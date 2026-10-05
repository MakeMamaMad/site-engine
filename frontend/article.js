// Legacy article.html?i=... compatibility shim.
// Old index-based URLs are not indexable; when possible, send users to the stable slug URL.
(function () {
  const NEWS_URLS = ["data/news.json", "frontend/data/news.json"];
  const articleEl = document.getElementById("article");

  function show(message) {
    if (!articleEl) return;
    articleEl.innerHTML =
      '<div class="empty-state"><h1>Материал перенесён</h1><p>' +
      message +
      '</p><p><a href="/" class="news-card-link">Перейти к ленте новостей</a></p></div>';
  }

  async function init() {
    const params = new URLSearchParams(window.location.search);
    const index = Number.parseInt(params.get("i") || "", 10);
    if (!Number.isFinite(index) || index < 0) {
      show("Старый адрес больше не используется.");
      return;
    }

    for (const url of NEWS_URLS) {
      try {
        const response = await fetch(url, { cache: "default" });
        if (!response.ok) continue;
        const data = await response.json();
        const items = Array.isArray(data) ? data : (data.items || []);
        const item = items[index];
        const slug = item && String(item.slug || "").trim();
        if (slug) {
          // Keep utm_* tags so Metrika still credits the original channel.
          const keep = new URLSearchParams();
          params.forEach((v, k) => { if (k.startsWith("utm_")) keep.set(k, v); });
          const qs = keep.toString();
          window.location.replace("/news/" + encodeURIComponent(slug) + "/" + (qs ? "?" + qs : ""));
          return;
        }
      } catch (_) {}
    }

    show("Не удалось определить новый адрес материала.");
  }

  document.addEventListener("DOMContentLoaded", init);
})();
