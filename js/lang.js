// 排行榜、貓咪牆共用的語言切換（首頁、關於頁有自己的 setLang）
// 用法：
//   <script src="js/lang.js"></script>
//   LCLang.init(DICT, apply)   DICT = { zh: {...}, en: {...}, ja: {...} }
//   LCLang.t('key')            取目前語言的文字（找不到用中文）
//   apply(lang)                切換語言時呼叫：更新畫面上動態產生的文字
// 靜態文字加 data-i18n="key"（innerHTML）會自動換
(function () {
  var dict = { zh: {} }, onApply = null;
  function lang() {
    try { var l = localStorage.getItem('lang'); return l === 'en' || l === 'ja' ? l : 'zh'; } catch (e) { return 'zh'; }
  }
  function t(key) {
    var l = lang();
    return (dict[l] && dict[l][key] != null) ? dict[l][key] : (dict.zh[key] != null ? dict.zh[key] : key);
  }
  function paint() {
    var l = lang();
    document.documentElement.lang = l === 'zh' ? 'zh-TW' : l;
    document.querySelectorAll('[data-i18n]').forEach(function (el) { el.innerHTML = t(el.getAttribute('data-i18n')); });
    document.querySelectorAll('.lang-btn[data-lang]').forEach(function (b) { b.classList.toggle('active', b.dataset.lang === l); });
    if (dict.zh.page_title) document.title = t('page_title');
    if (onApply) onApply(l);
  }
  function set(l) {
    var changed = l !== lang();
    try { localStorage.setItem('lang', l); } catch (e) {}
    if (changed && window.LC) window.LC.track('language_change', { new_language: l });
    paint();
  }
  // 在上方選單加「中／EN／日」（和首頁同樣的樣式）
  function addSwitcher() {
    var nav = document.querySelector('.topnav');
    var right = document.getElementById('nav-right');
    if (!nav || !right || nav.querySelector('.lang-switcher')) return;
    var box = document.createElement('div');
    box.className = 'lang-switcher';
    box.innerHTML = '<button class="lang-btn" data-lang="zh" type="button">中</button>'
      + '<button class="lang-btn" data-lang="en" type="button">EN</button>'
      + '<button class="lang-btn" data-lang="ja" type="button">日</button>';
    right.parentNode.insertBefore(box, right);
    box.addEventListener('click', function (e) {
      var b = e.target.closest('.lang-btn');
      if (b) set(b.dataset.lang);
    });
  }
  function init(d, apply) {
    dict = d; onApply = apply || null;
    addSwitcher();
    paint();
  }
  window.LCLang = { init: init, t: t, lang: lang, set: set };
})();
