// 自動對焦：找出照片中動物的位置，裁切時以牠為中心（一般 <script> 載入，掛在 window.Focus）
// 偵測在使用者瀏覽器內執行（TensorFlow.js + COCO-SSD），照片不會送到其他地方。
(function () {
  var TFJS = 'https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.20.0/dist/tf.min.js';
  var COCO = 'https://cdn.jsdelivr.net/npm/@tensorflow-models/coco-ssd@2.2.3/dist/coco-ssd.min.js';
  // COCO-SSD 能辨識的動物；蜷成一團的貓常被認成狗，所以全部接受
  var ANIMALS = ['cat', 'dog', 'bird', 'horse', 'sheep', 'cow', 'bear', 'teddy bear'];
  var modelPromise = null;

  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      if (document.querySelector('script[src="' + src + '"]')) return resolve();
      var s = document.createElement('script');
      s.src = src; s.onload = resolve; s.onerror = reject;
      document.head.appendChild(s);
    });
  }

  // 預先載入（進入上傳頁就呼叫，第一次約十幾秒）；失敗時回傳 null，不影響選號
  function preload() {
    if (!modelPromise) {
      modelPromise = loadScript(TFJS)
        .then(function () { return loadScript(COCO); })
        .then(function () { return window.cocoSsd.load({ base: 'lite_mobilenet_v2' }); })
        .catch(function (e) { console.warn('Focus: 模型載入失敗', e); return null; });
    }
    return modelPromise;
  }

  // 把偵測結果轉成 0~1 的相對座標；同類動物取聯集（例如兩隻貓）
  function pickFocus(preds, w, h) {
    var animals = (preds || []).filter(function (p) { return ANIMALS.indexOf(p.class) !== -1 && p.score >= 0.35; });
    if (!animals.length) return null;
    var best = animals.slice().sort(function (a, b) {
      return b.score * b.bbox[2] * b.bbox[3] - a.score * a.bbox[2] * a.bbox[3];
    })[0];
    // 與最佳那隻同類、且信心不太低的一起算進來
    var group = animals.filter(function (p) { return p.class === best.class && p.score >= best.score * 0.6; });
    var x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    group.forEach(function (p) {
      x0 = Math.min(x0, p.bbox[0]); y0 = Math.min(y0, p.bbox[1]);
      x1 = Math.max(x1, p.bbox[0] + p.bbox[2]); y1 = Math.max(y1, p.bbox[1] + p.bbox[3]);
    });
    var r = function (v) { return Math.round(Math.min(1, Math.max(0, v)) * 1000) / 1000; };
    return { x: r(x0 / w), y: r(y0 / h), w: r((x1 - x0) / w), h: r((y1 - y0) / h), label: best.class, score: r(best.score) };
  }

  // 偵測：回傳 { focus, isAnimal }；模型不可用時 isAnimal 為 null（交給其他判斷）
  function detect(img) {
    return preload().then(function (model) {
      if (!model) return { focus: null, isAnimal: null };
      return model.detect(img, 10, 0.2).then(function (preds) {
        var f = pickFocus(preds, img.naturalWidth || img.width, img.naturalHeight || img.height);
        return { focus: f, isAnimal: !!f };
      });
    }).catch(function (e) {
      console.warn('Focus: 偵測失敗', e);
      return { focus: null, isAnimal: null };
    });
  }

  // 依版位比例 aspect（寬/高）計算裁切範圍（原圖像素）
  // - 盡量保留畫面，動物置中
  // - 動物很小時稍微放大，但最多放大到原本可裁範圍的 60%（避免畫質太差）
  function cropRect(imgW, imgH, focus, aspect) {
    var maxW, maxH;
    if (imgW / imgH > aspect) { maxH = imgH; maxW = imgH * aspect; }
    else { maxW = imgW; maxH = imgW / aspect; }
    var cw = maxW, ch = maxH, cx = imgW / 2, cy = imgH / 2;
    if (focus && focus.w > 0 && focus.h > 0) {
      var fx = focus.x * imgW, fy = focus.y * imgH, fw = focus.w * imgW, fh = focus.h * imgH;
      cx = fx + fw / 2; cy = fy + fh / 2;
      // 動物四周各留 20% 的空間，換算成符合比例的大小
      var needW = Math.max(fw * 1.4, fh * 1.4 * aspect);
      var scale = Math.min(1, Math.max(0.6, needW / maxW));
      cw = maxW * scale; ch = maxH * scale;
    }
    var x = Math.min(Math.max(cx - cw / 2, 0), imgW - cw);
    var y = Math.min(Math.max(cy - ch / 2, 0), imgH - ch);
    return { x: x, y: y, w: cw, h: ch };
  }

  // 決定照片怎麼放進版位（slotW × slotH）：
  // - cover：裁切放大填滿（一般情況）
  // - contain：主角太寬或太高、裁切會切掉超過 2 成時，把主角完整放進框，
  //   空出的部分用同一張照片的模糊版本補滿（例如橫向照片兩隻貓分別在左右兩端，放進直式框）
  // 沒有對焦資訊時，把整張照片當成主角，避免舊紀錄或偵測不到時切掉太多
  var MIN_COVERAGE = 0.8;
  function layout(imgW, imgH, focus, slotW, slotH) {
    var aspect = slotW / slotH;
    var f = (focus && focus.w > 0 && focus.h > 0) ? focus : { x: 0, y: 0, w: 1, h: 1 };
    var c = cropRect(imgW, imgH, focus || null, aspect);
    var fw = f.w * imgW, fh = f.h * imgH;
    var coverage = Math.min(1, c.w / fw, c.h / fh);
    if (coverage >= MIN_COVERAGE) return { mode: 'cover', src: c, coverage: coverage };
    // 主角四周留 4% 邊，限制在照片範圍內
    var pad = 0.04;
    var sx = Math.max(0, (f.x - pad) * imgW), sy = Math.max(0, (f.y - pad) * imgH);
    var ex = Math.min(imgW, (f.x + f.w + pad) * imgW), ey = Math.min(imgH, (f.y + f.h + pad) * imgH);
    var sw = ex - sx, sh = ey - sy;
    var scale = Math.min(slotW / sw, slotH / sh);
    var dw = sw * scale, dh = sh * scale;
    return { mode: 'contain', coverage: coverage, src: { x: sx, y: sy, w: sw, h: sh },
             dst: { x: (slotW - dw) / 2, y: (slotH - dh) / 2, w: dw, h: dh } };
  }

  window.Focus = { preload: preload, detect: detect, pickFocus: pickFocus, cropRect: cropRect, layout: layout };
})();
