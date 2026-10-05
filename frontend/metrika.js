// Owner opt-out: open any page with ?notrack=1 once in a browser to stop
// counting visits from it (?notrack=0 turns counting back on).
(function(){
  try {
    var q = new URLSearchParams(location.search).get('notrack');
    if (q === '1') localStorage.setItem('specavto_notrack', '1');
    if (q === '0') localStorage.removeItem('specavto_notrack');
    if (localStorage.getItem('specavto_notrack') === '1') { window.__specavtoNoTrack = true; }
  } catch (e) {}
  // Automated browsers: about half of all "visits" were headless crawlers
  // (Singapore, 1 second, always on /article.html). They skew every report.
  try {
    if (navigator.webdriver || /HeadlessChrome|Lighthouse|PhantomJS|Puppeteer|Playwright/i.test(navigator.userAgent)) {
      window.__specavtoNoTrack = true;
    }
  } catch (e) {}
  // /article.html is only a legacy redirect to /news/<slug>/; a real reader is
  // counted on the page they land on, so the redirect page itself is not.
  if (/\/article\.html$/.test(location.pathname)) window.__specavtoNoTrack = true;
})();
if (!window.__specavtoNoTrack) {
(function(m,e,t,r,i,k,a){
  m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
  m[i].l=1*new Date();
  k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a);
})(window, document, "script", "https://mc.yandex.ru/metrika/tag.js", "ym");

ym(106240080, "init", {
  clickmap: true,
  trackLinks: true,
  accurateTrackBounce: true
});
}
