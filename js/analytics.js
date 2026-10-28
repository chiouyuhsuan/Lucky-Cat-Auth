// GA4 追蹤（一般 <script> 載入，掛在 window.LC）
// 每個頁面在 <head> 載入這支檔案；頁面程式用 LC.track(事件名稱, 參數) 送事件。
//
// 隱私：不送 Email、貓名、照片、號碼。使用者 ID 只送 Firebase 帳號編號（GA4 允許，不屬於個資）。
// 排除自己的流量：網址加 ?internal=1 打開一次，之後這個瀏覽器完全不送資料；?internal=0 取消。
// 檢查用：網址加 ?ga_debug=1，事件會出現在 GA4「DebugView」，並印在瀏覽器主控台。
(function () {
  var ID = 'G-NT2E29RTNT';
  var q = location.search;

  function ls(get, k, v) {
    try {
      if (get) return localStorage.getItem(k);
      if (v === null) localStorage.removeItem(k); else localStorage.setItem(k, v);
    } catch (e) { return null; }
  }
  if (/[?&]internal=1\b/.test(q)) ls(false, 'lc_internal', '1');
  if (/[?&]internal=0\b/.test(q)) ls(false, 'lc_internal', null);

  var debug = /[?&]ga_debug=1\b/.test(q);
  var internal = ls(true, 'lc_internal') === '1';
  var localDev = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(location.hostname) || location.protocol === 'file:';
  var enabled = !internal && (!localDev || debug);

  window.dataLayer = window.dataLayer || [];
  function gtag() { window.dataLayer.push(arguments); }
  window.gtag = gtag;

  var loggedIn = 'unknown';
  function lang() { return ls(true, 'lang') || 'zh'; }

  if (enabled) {
    var s = document.createElement('script');
    s.async = true;
    s.src = 'https://www.googletagmanager.com/gtag/js?id=' + ID;
    document.head.appendChild(s);
    gtag('js', new Date());
    var cfg = { site_language: lang() };
    if (debug) cfg.debug_mode = true;
    gtag('config', ID, cfg);
  }

  function track(name, params) {
    var p = {};
    for (var k in (params || {})) if (params[k] !== undefined && params[k] !== null) p[k] = params[k];
    p.site_language = lang();
    p.logged_in = loggedIn;
    if (debug) console.log('[GA4]', enabled ? '' : '(未送出)', name, p);
    if (enabled) gtag('event', name, p);
  }

  // 登入狀態：uid 為 null 代表未登入
  function setUser(uid) {
    loggedIn = uid ? 'yes' : 'no';
    if (!enabled) return;
    gtag('set', { user_id: uid || null });
    gtag('set', 'user_properties', { logged_in: loggedIn, site_language: lang() });
  }

  // ── 目前頁面名稱：首頁用虛擬頁面（upload／result…），其他頁用檔名 ──
  var fileName = (location.pathname.replace(/^.*\//, '') || 'index.html').replace(/\.html$/, '');
  var lastPage = null;
  function pageName() { return lastPage || (fileName === 'index' ? 'home' : fileName); }

  // ── 停留與捲動：每個（虛擬）頁面記錄可見秒數與最大捲動深度，離開時送 page_leave ──
  var pv = null;
  function startPv() {
    pv = { name: pageName(), start: Date.now(), visibleMs: 0, visibleSince: document.hidden ? null : Date.now(), maxScroll: 0, sent: {}, sections: {} };
    observeSections();
  }
  function visibleSeconds() {
    var ms = pv.visibleMs + (pv.visibleSince ? Date.now() - pv.visibleSince : 0);
    return Math.round(ms / 1000);
  }
  function endPv(reason) {
    if (!pv || pv.ended) return;
    pv.ended = true;
    track('page_leave', { page_name: pv.name, engaged_seconds: visibleSeconds(), max_scroll_percent: pv.maxScroll, leave_reason: reason });
  }
  document.addEventListener('visibilitychange', function () {
    if (!pv) return;
    if (document.hidden) {
      if (pv.visibleSince) { pv.visibleMs += Date.now() - pv.visibleSince; pv.visibleSince = null; }
      endPv('hidden');
    } else {
      // 回到分頁：視為同一頁的新一段停留（已送過的捲動深度、區塊曝光不重送）
      var keep = pv; startPv();
      pv.name = keep.name; pv.sent = keep.sent; pv.sections = keep.sections; pv.maxScroll = keep.maxScroll;
    }
  });
  window.addEventListener('pagehide', function () { endPv('unload'); });

  // 捲動深度 25／50／75／90／100%
  var MARKS = [25, 50, 75, 90, 100];
  function onScroll() {
    if (!pv) return;
    var h = document.documentElement.scrollHeight - window.innerHeight;
    var pct = h <= 0 ? 100 : Math.min(100, Math.round(window.scrollY / h * 100));
    if (pct > pv.maxScroll) pv.maxScroll = pct;
    MARKS.forEach(function (m) {
      if (pct >= m && !pv.sent[m] && h > 200) {   // 頁面太短（幾乎不用捲）不算
        pv.sent[m] = 1;
        track('scroll_depth', { percent_scrolled: m, page_name: pv.name });
      }
    });
  }
  var scrollTimer = null;
  window.addEventListener('scroll', function () {
    if (scrollTimer) return;
    scrollTimer = setTimeout(function () { scrollTimer = null; onScroll(); }, 250);
  }, { passive: true });

  // 區塊曝光：有 data-ga-section 的區塊出現在畫面一半以上，每次瀏覽記一次
  var io = null;
  function observeSections() {
    if (!('IntersectionObserver' in window)) return;
    if (io) io.disconnect();
    io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        var id = en.target.getAttribute('data-ga-section');
        if (en.isIntersecting && pv && !pv.sections[id] && en.target.offsetParent !== null) {
          pv.sections[id] = 1;
          track('section_view', { section_name: id, page_name: pv.name, seconds_since_page_view: Math.round((Date.now() - pv.start) / 1000) });
        }
      });
    }, { threshold: 0.5 });
    document.querySelectorAll('[data-ga-section]').forEach(function (el) { io.observe(el); });
  }

  // 單頁式的換頁（首頁的上傳、結果、紀錄…）：送虛擬頁面瀏覽
  function page(name, first) {
    if (name === lastPage) return;
    var isFirst = lastPage === null;
    if (!isFirst) endPv('navigate');
    lastPage = name;
    startPv();
    if (isFirst && first) return;   // 載入頁面時 config 已送過一次
    track('page_view', {
      page_title: document.title + ' | ' + name,
      page_location: location.origin + location.pathname + '#' + name,
      page_name: name,
    });
  }
  if (fileName !== 'index') {
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', startPv); else startPv();
  }

  // ── 所有點擊：記錄點了哪個元件（只記元件代號，不記畫面文字，避免帶到貓名等內容）──
  var SKIP_FN = { ga: 1, event: 1, window: 1, closeModal: 0 };
  function uiId(el) {
    if (el.id) return el.id;
    if (el.dataset && el.dataset.act) return 'act:' + el.dataset.act;
    if (el.dataset && el.dataset.i18n) return 'i18n:' + el.dataset.i18n;
    var oc = el.getAttribute('onclick');
    if (oc) {
      var fns = (oc.match(/[A-Za-z_$][\w$]*(?=\s*\()/g) || []).filter(function (f) { return !SKIP_FN[f]; });
      var arg = (oc.match(/\(\s*'([\w-]{1,24})'/) || [])[1];
      if (fns.length) return fns[fns.length - 1] + (arg ? ':' + arg : '');
    }
    if (el.tagName === 'A') return 'link:' + (el.getAttribute('href') || '').replace(/[?#].*$/, '');
    var cls = (el.className && typeof el.className === 'string') ? el.className.split(/\s+/)[0] : '';
    return (el.tagName || '').toLowerCase() + (cls ? '.' + cls : '');
  }
  var CLICKABLE = 'button,a[href],[onclick],[role=button],.cat-card,.lot-item,.lang-btn,.nav-user-menu,.nav-dropdown-item,input[type=file],label';
  document.addEventListener('click', function (e) {
    var el = e.target.closest && e.target.closest(CLICKABLE);
    if (!el) return;
    var area = el.closest('[data-ga-section]');
    track('ui_click', {
      ui_id: uiId(el).slice(0, 80),
      ui_type: (el.tagName || '').toLowerCase(),
      ui_section: area ? area.getAttribute('data-ga-section') : (el.closest('nav') ? 'nav' : el.closest('.modal-overlay,.modal-box,.lightbox') ? 'modal' : ''),
      page_name: pageName(),
    });
  }, true);

  // 程式錯誤：使用者可能因此卡住
  var errCount = 0;
  window.addEventListener('error', function (e) {
    if (errCount++ >= 5 || !e.message) return;
    track('js_error', { error_message: String(e.message).slice(0, 100), error_source: String(e.filename || '').replace(/^.*\//, '').slice(0, 60) });
  });
  window.addEventListener('unhandledrejection', function (e) {
    if (errCount++ >= 5) return;
    var r = e.reason || {};
    track('js_error', { error_message: String(r.code || r.message || r).slice(0, 100), error_source: 'promise' });
  });

  window.LC = { track: track, setUser: setUser, page: page, pageName: pageName, observeSections: observeSections,
                enabled: enabled, internal: internal, ID: ID };
})();
