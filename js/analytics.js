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

  // 單頁式的換頁（首頁的上傳、結果、紀錄…）：送虛擬頁面瀏覽
  var lastPage = null;
  function page(name, first) {
    if (name === lastPage) return;
    var isFirst = lastPage === null;
    lastPage = name;
    if (isFirst && first) return;   // 載入頁面時 config 已送過一次
    track('page_view', {
      page_title: document.title + ' | ' + name,
      page_location: location.origin + location.pathname + '#' + name,
      page_name: name,
    });
  }

  // 站內連結（加強型評估只算外部連結）：選單、開始選號、CTA
  document.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a || a.host !== location.host) return;
    var cls = a.classList.contains('nav-link') ? 'nav' : a.classList.contains('nav-cta') ? 'nav_cta'
            : a.classList.contains('cta-btn') ? 'cta' : 'link';
    track('internal_link_click', { link_area: cls, link_path: a.pathname.replace(/^.*\//, '') || 'index.html' });
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

  window.LC = { track: track, setUser: setUser, page: page, enabled: enabled, internal: internal, ID: ID };
})();
