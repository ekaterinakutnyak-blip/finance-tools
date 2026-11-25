/* investtools.pro — единая верхняя навигация. */
(function () {
  try {
    if (document.querySelector('#site-nav, .nav')) return;
    var css =
      '#site-nav{position:sticky;top:0;z-index:9999;display:flex;align-items:center;justify-content:space-between;' +
      'gap:10px;flex-wrap:wrap;background:#FFFFFF;border-bottom:1px solid #E5E4DF;' +
      'padding:8px 16px;font-family:"DM Sans",system-ui,-apple-system,sans-serif;' +
      'box-shadow:0 1px 3px rgba(0,0,0,0.03)}' +
      '#site-nav a{text-decoration:none;font-size:0.82rem;color:#6B6A65;transition:color .15s}' +
      '#site-nav a:hover{color:#2D5A3D}' +
      '#site-nav .sn-home{font-weight:600;color:#2D5A3D}' +
      '#site-nav .sn-links{display:flex;gap:16px;flex-wrap:wrap}' +
      '@media(max-width:480px){#site-nav{padding:7px 12px;gap:6px}#site-nav a{font-size:0.78rem}#site-nav .sn-links{gap:12px}}';
    var style = document.createElement('style');
    style.textContent = css;
    document.head.appendChild(style);
    var bar = document.createElement('nav');
    bar.id = 'site-nav';
    bar.innerHTML =
      '<a class="sn-home" href="/">← На главную</a>' +
      '<span class="sn-links">' +
      '<a href="/index.html">Калькуляторы</a>' +
      '<a href="/articles.html">Статьи</a>' +
      '<a href="/novosti.html">Новости</a>' +
      '</span>';
    document.body.insertBefore(bar, document.body.firstChild);
  } catch (e) {}
})();

/* investtools.pro — трекинг воронки (Яндекс.Метрика 109013741). Не влияет на навигацию. */
(function () {
  try {
    var YM = 109013741;
    document.addEventListener('click', function (ev) {
      try {
        var a = ev.target && ev.target.closest ? ev.target.closest('a[href]') : null;
        if (!a) return;
        var href = a.getAttribute('href') || '';
        if (typeof window.ym !== 'function') return;
        var goal = null;
        if (href.indexOf('t.me/k_invest_channel_bot') !== -1) goal = 'buy_click';
        else if (href.indexOf('oplata.html') !== -1) goal = 'pay_page';
        else if (href.indexOf('#pricing') !== -1) goal = 'pro_pricing';
        else if (href.indexOf('#free') !== -1) goal = 'free_tools';
        else if (href.indexOf('/pro/') !== -1) goal = 'pro_tool';
        if (goal) window.ym(YM, 'reachGoal', goal);
      } catch (e) {}
    }, true);
  } catch (e) {}
})();

/* investtools.pro — уведомление об использовании cookie и веб-аналитики.
   Это уведомление, а не блокирующее согласие: счётчик Яндекс.Метрики встроен
   в сами страницы и запускается раньше этого файла. Плашка показывается один раз
   и больше не появляется. Если браузер запрещает localStorage, плашка просто
   покажется снова в следующий раз — ничего не ломается. */
(function () {
  var KEY = 'cookie_notice_seen';
  try {
    if (localStorage.getItem(KEY) === '1') return;
  } catch (e) {}

  function build() {
    try {
      if (document.getElementById('cookie-notice')) return;
      var css =
        '#cookie-notice{position:fixed;left:0;right:0;bottom:0;z-index:10000;display:flex;align-items:center;' +
        'justify-content:center;gap:14px;flex-wrap:wrap;background:#FFFFFF;border-top:1px solid #E5E4DF;' +
        'box-shadow:0 -1px 6px rgba(0,0,0,.05);padding:11px 16px;' +
        'font-family:"DM Sans",system-ui,-apple-system,sans-serif;font-size:0.8rem;color:#6B6A65;line-height:1.45}' +
        '#cookie-notice a{color:#2D5A3D;text-decoration:underline}' +
        '#cookie-notice button{font-family:inherit;font-size:0.8rem;font-weight:600;color:#fff;background:#2D5A3D;' +
        'border:none;border-radius:8px;padding:7px 18px;cursor:pointer;flex:0 0 auto}' +
        '#cookie-notice button:hover{filter:brightness(1.08)}' +
        '@media(max-width:560px){#cookie-notice{gap:9px;padding:10px 12px;font-size:0.76rem;text-align:center}}';
      var st = document.createElement('style');
      st.textContent = css;
      document.head.appendChild(st);

      var box = document.createElement('div');
      box.id = 'cookie-notice';
      box.innerHTML =
        '<span>Сайт использует файлы cookie и сервис статистики Яндекс.Метрика. ' +
        'Подробнее — в <a href="/personal-data.html">политике обработки данных</a>.</span>' +
        '<button type="button">Понятно</button>';
      box.querySelector('button').onclick = function () {
        try { localStorage.setItem(KEY, '1'); } catch (e) {}
        box.remove();
      };
      document.body.appendChild(box);
    } catch (e) {}
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
})();

/* investtools.pro — строка с правовыми документами внизу каждой страницы. */
(function () {
  function build() {
    try {
      if (document.getElementById('site-legal')) return;
      var css =
        '#site-legal{margin:28px 0 0;padding:12px 16px 16px;border-top:1px solid #E5E4DF;' +
        'text-align:center;font-family:"DM Sans",system-ui,-apple-system,sans-serif;' +
        'font-size:0.74rem;color:#8a8883;line-height:1.5}' +
        '#site-legal a{color:#8a8883;text-decoration:none;border-bottom:1px solid #E5E4DF}' +
        '#site-legal a:hover{color:#2D5A3D}';
      var st = document.createElement('style');
      st.textContent = css;
      document.head.appendChild(st);
      var box = document.createElement('div');
      box.id = 'site-legal';
      box.innerHTML =
        'ИП Кутняк Екатерина Георгиевна · ИНН 503211905008 · ' +
        '<a href="/oferta.html">Оферта</a> · ' +
        '<a href="/personal-data.html">Обработка данных</a>';
      document.body.appendChild(box);
    } catch (e) {}
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', build);
  } else {
    build();
  }
})();
