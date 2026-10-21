// 輸出安全工具：任何來自資料庫或使用者的文字，插進 HTML 前都要經過這裡。
// 用一般 <script> 載入，掛在 window.Safe 上，模組與非模組腳本都能用。
(function () {
  var MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' };

  // 跳脫成可放進 HTML 內文或屬性值（需用引號包住）的字串
  function esc(v) {
    if (v === null || v === undefined) return '';
    return String(v).replace(/[&<>"'`]/g, function (c) { return MAP[c]; });
  }

  // 圖片網址白名單：只允許 data:image/（Base64 圖片）與 https://，其他一律丟棄
  function img(src) {
    if (typeof src !== 'string') return '';
    var s = src.trim();
    if (/^data:image\/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=]+$/i.test(s)) return s;
    if (/^https:\/\/[^\s"'<>`]+$/i.test(s)) return esc(s);
    return '';
  }

  // 數字：資料庫內容不可信，一律轉成真正的整數
  function int(v) {
    var n = parseInt(v, 10);
    return isFinite(n) ? n : 0;
  }

  // 樂透球號碼：轉整數後補零
  function ball(v) {
    return String(int(v)).padStart(2, '0');
  }

  // 國碼：只接受兩個英文字母
  function cc(v) {
    return (typeof v === 'string' && /^[A-Za-z]{2}$/.test(v)) ? v.toUpperCase() : '';
  }

  window.Safe = { esc: esc, img: img, int: int, ball: ball, cc: cc };
})();
