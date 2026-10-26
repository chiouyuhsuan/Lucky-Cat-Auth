// 重複照片判斷（一般 <script> 載入，掛在 window.Dedupe）
// 做法：差異雜湊（dHash）。把照片縮成 9×8 灰階，比較左右相鄰像素的明暗，得到 64 位元的「指紋」。
// 兩張照片指紋不同的位元數 ≤ THRESHOLD 就視為同一張（同一張重複上傳、或幾乎一樣的連拍）。
// 同一隻貓的不同照片指紋差異大，不會被合併。
(function () {
  var THRESHOLD = 6;

  // gray：長度 72（9 寬 × 8 高）的灰階值陣列 → 64 個 0/1
  function hashFromGray(gray) {
    var bits = [];
    for (var y = 0; y < 8; y++) {
      for (var x = 0; x < 8; x++) bits.push(gray[y * 9 + x] < gray[y * 9 + x + 1] ? 1 : 0);
    }
    return bits;
  }

  function distance(a, b) {
    var d = 0;
    for (var i = 0; i < 64; i++) if (a[i] !== b[i]) d++;
    return d;
  }

  var cache = {};
  function hashImage(src) {
    if (cache[src]) return cache[src];
    cache[src] = new Promise(function (resolve) {
      var im = new Image();
      im.onload = function () {
        var cv = document.createElement('canvas'); cv.width = 9; cv.height = 8;
        var ctx = cv.getContext('2d');
        ctx.drawImage(im, 0, 0, 9, 8);
        var px = ctx.getImageData(0, 0, 9, 8).data, gray = [];
        for (var i = 0; i < 72; i++) gray.push(px[i * 4] * 0.299 + px[i * 4 + 1] * 0.587 + px[i * 4 + 2] * 0.114);
        resolve(hashFromGray(gray));
      };
      im.onerror = function () { resolve(null); };
      im.src = src;
    });
    return cache[src];
  }

  // items 依新到舊排列；同一位使用者的重複照片只留最新一筆，並記下合併了幾筆
  // keyOf(item) 取照片、ownerOf(item) 取使用者
  function dedupe(items, keyOf, ownerOf) {
    return Promise.all(items.map(function (it) { return hashImage(keyOf(it)); })).then(function (hashes) {
      var kept = [], keptHash = [];
      items.forEach(function (it, i) {
        var h = hashes[i];
        for (var k = 0; h && k < kept.length; k++) {
          if (ownerOf(kept[k].item) === ownerOf(it) && keptHash[k] && distance(keptHash[k], h) <= THRESHOLD) {
            kept[k].dupes.push(it);
            return;
          }
        }
        kept.push({ item: it, dupes: [] }); keptHash.push(h);
      });
      return kept;
    });
  }

  window.Dedupe = { hashFromGray: hashFromGray, distance: distance, dedupe: dedupe, THRESHOLD: THRESHOLD };
})();
