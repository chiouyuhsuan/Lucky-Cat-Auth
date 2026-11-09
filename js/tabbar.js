// 下方五個分頁鈕（首頁、排行榜、上傳、貓咪牆、我的帳戶），四個頁面共用
// 用法：<script src="js/tabbar.js"></script>，放在 </body> 前
// 首頁裡的「上傳」「我的帳戶」直接切換分頁；其他頁面先記下要去哪裡再回首頁（沿用 sessionStorage 'goto'）
(function () {
  var TXT = {
    zh: { home: '首頁', rank: '排行榜', upload: '上傳', wall: '貓咪牆', me: '我的帳戶' },
    en: { home: 'Home', rank: 'Leaderboard', upload: 'Upload', wall: 'Cat Wall', me: 'My Account' },
    ja: { home: 'ホーム', rank: 'ランキング', upload: 'アップロード', wall: '猫ウォール', me: 'マイアカウント' },
  };
  var ICON = {
    home: '<path d="M3 11l9-7 9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    rank: '<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>',
    upload: '<path d="M12 5v14M5 12h14"/>',
    wall: '<rect x="3" y="3" width="8" height="8" rx="2"/><rect x="13" y="3" width="8" height="8" rx="2"/><rect x="3" y="13" width="8" height="8" rx="2"/><rect x="13" y="13" width="8" height="8" rx="2"/>',
    me: '<path d="M5 20c1-4 4-6 7-6s6 2 7 6"/><path d="M8 6l1.5-3L12 5l2.5-2L16 6"/><circle cx="12" cy="9" r="4"/>',
  };
  var file = (location.pathname.split('/').pop() || 'index.html');
  var onIndex = file === '' || file === 'index.html';
  var here = file.indexOf('rank') === 0 ? 'rank' : file.indexOf('wall') === 0 ? 'wall' : onIndex ? 'home' : '';

  function lang() { try { var l = localStorage.getItem('lang'); return TXT[l] ? l : 'zh'; } catch (e) { return 'zh'; } }
  function svg(k, w) {
    return '<svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="' + w + '" stroke-linecap="round" stroke-linejoin="round">' + ICON[k] + '</svg>';
  }

  var nav = document.createElement('nav');
  nav.className = 'tabbar';
  nav.setAttribute('aria-label', 'menu');
  document.body.appendChild(nav);

  function render() {
    var t = TXT[lang()];
    nav.innerHTML =
        '<a href="index.html" data-tab="home">' + svg('home', 2) + '<b></b></a>'
      + '<a href="rank.html" data-tab="rank">' + svg('rank', 2) + '<b></b></a>'
      + '<a href="index.html" data-tab="upload" class="tab-main"><span>' + svg('upload', 2.4) + '</span><b></b></a>'
      + '<a href="wall.html" data-tab="wall">' + svg('wall', 2) + '<b></b></a>'
      + '<a href="index.html" data-tab="me">' + svg('me', 2) + '<b></b></a>';
    nav.querySelectorAll('a').forEach(function (a) {
      var k = a.dataset.tab;
      a.querySelector('b').textContent = t[k];
      a.querySelector('b').style.fontWeight = 'inherit';
      a.setAttribute('aria-label', t[k]);
    });
    mark();
  }

  // 首頁裡目前顯示哪個分頁
  function mark() {
    var cur = here;
    if (onIndex) {
      var act = document.querySelector('.page.active');
      var id = act ? act.id.replace('page-', '') : 'home';
      cur = id === 'profile' ? 'me' : id === 'home' ? 'home' : 'upload';
    }
    nav.querySelectorAll('a').forEach(function (a) {
      var on = a.dataset.tab === cur;
      a.classList.toggle('on', on && a.dataset.tab !== 'upload');
      if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
    });
  }

  nav.addEventListener('click', function (e) {
    var a = e.target.closest('a[data-tab]');
    if (!a) return;
    var k = a.dataset.tab;
    if (window.LC) window.LC.track('ui_click', { element: 'tabbar_' + k });
    if (k !== 'upload' && k !== 'me' && !(onIndex && k === 'home')) return;   // 一般連結
    e.preventDefault();
    if (onIndex) {
      if (k === 'home') window.showPage('home');
      else if (k === 'me') window.showPage('profile');
      else if (window.handleUploadClick) window.handleUploadClick();
      mark();
      return;
    }
    try { sessionStorage.setItem('goto', k === 'me' ? 'profile' : 'upload'); } catch (err) {}
    location.href = 'index.html';
  });

  // 首頁換分頁、切換語言時更新
  if (onIndex) {
    var pages = document.querySelectorAll('.page');
    var mo = new MutationObserver(mark);
    pages.forEach(function (p) { mo.observe(p, { attributes: true, attributeFilter: ['class'] }); });
  }
  document.addEventListener('click', function (e) { if (e.target.closest && e.target.closest('.lang-btn')) setTimeout(render, 0); });
  render();
  window.Tabbar = { render: render };

  // ── App 內建瀏覽器（Threads、IG、FB、LINE）：只記 GA，不顯示提醒 ─────
  // App 內建瀏覽器裡 Google 不允許登入、關掉 App 後登入狀態常被清掉，先記錄有多少人從這裡開
  var IN_APP = /Barcelona|Instagram|FBAN|FBAV|FB_IAB|FBIOS|Line\/|; wv\)/i;
  if (IN_APP.test(navigator.userAgent) && window.LC) {
    var m = navigator.userAgent.match(/Barcelona|Instagram|FBAN|FBAV|FB_IAB|FBIOS|Line/i);
    var app = m ? ({ barcelona: 'threads', fban: 'facebook', fbav: 'facebook', fb_iab: 'facebook', fbios: 'facebook' }[m[0].toLowerCase()] || m[0].toLowerCase()) : 'webview';
    window.LC.track('in_app_browser', { app: app, page: here || 'other' });
  }
})();
