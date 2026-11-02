// 分享圖卡（一般 <script> 載入，掛在 window.Card）
// 依使用者提供的模板：橘色腳印外框、米色卡片、大標、貓照、貓名與抽選日期、號碼球、開獎資訊、理性購買警語
// 尺寸：9:16（限時動態）1080×1920、4:5（貼文）1080×1350
(function () {
  var SIZES = { '9:16': [1080, 1920], '4:5': [1080, 1350] };
  // 每天換一個顏色：依「選號日」是星期幾，週一紅、週二橙、週三黃、週四綠、週五藍、週六靛、週日紫
  // 同一張選號之後再打開，顏色不變
  var BROWN = { title: '#3A271B', text: '#4A3426', ballText: '#2E1F14' };
  var NAVY = { title: '#1F2A44', text: '#2D3A55', ballText: '#1B2238' };
  var PLUM = { title: '#2E2140', text: '#3B2D52', ballText: '#24183A' };
  var THEMES = {
    red:    mk('#E8676B', '#F39C9E', '#F09A9C', '#F7B5B6', '#E46D71', '#FFF5F4', '#FADADB', BROWN),
    orange: mk('#F6A85C', '#FBC98F', '#F3B36E', '#F9C27F', '#EF8E3A', '#FFF7EA', '#FBE3C4', BROWN),
    yellow: mk('#F2C230', '#F8DA7A', '#EEC64A', '#F9DE86', '#EDB520', '#FFFBEA', '#FBEDB8', BROWN),
    green:  mk('#6DBE7E', '#9FD7AB', '#8FCB9C', '#B5E1BF', '#6BB97C', '#F4FBF5', '#D5EEDB', NAVY),
    blue:   mk('#5AA7E0', '#93C6EE', '#8CC0E8', '#B3D7F3', '#5FA4DB', '#F3F9FE', '#D3E7F7', NAVY),
    indigo: mk('#5C6BC0', '#8F9AD7', '#9AA3DA', '#BEC5EB', '#8792D4', '#F5F6FD', '#DCE0F4', NAVY),
    purple: mk('#9B72CF', '#C0A3E3', '#BFA2E2', '#D7C5EF', '#AC8AD9', '#F9F5FE', '#E7DCF6', PLUM)
  };
  // getDay()：0＝週日
  var WEEK = ['purple', 'red', 'orange', 'yellow', 'green', 'blue', 'indigo'];
  function mk(frame, framePaw, line, ball, ballDark, card, empty, ink) {
    return { frame: frame, framePaw: framePaw, line: line, photoStroke: line, ball: ball, ballDark: ballDark,
      card: card, pawBox: card, empty: empty, title: ink.title, text: ink.text, ballText: ink.ballText };
  }
  // date：Date，或 'YYYY/MM/DD'、'YYYY.MM.DD'、'YYYY-MM-DD'；讀不到就用今天
  function themeName(date) {
    var d = date instanceof Date ? date : null;
    if (!d && date) {
      var m = String(date).match(/(\d{4})\D(\d{1,2})\D(\d{1,2})/);
      if (m) d = new Date(+m[1], +m[2] - 1, +m[3]);
    }
    if (!d || isNaN(d)) d = new Date();
    return WEEK[d.getDay()];
  }
  var FONT = '"Noto Sans TC","Noto Sans CJK TC","PingFang TC","Hiragino Sans","Microsoft JhengHei",sans-serif';

  function rr(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  // 腳印：一個大肉球＋四個小肉球
  function paw(ctx, cx, cy, s, color, rot) {
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(rot || 0); ctx.fillStyle = color;
    ctx.beginPath(); ctx.ellipse(0, s * 0.28, s * 0.36, s * 0.3, 0, 0, Math.PI * 2); ctx.fill();
    [[-0.42, -0.12, 0.13, 0.17, -0.35], [-0.16, -0.38, 0.14, 0.18, -0.12],
     [0.16, -0.38, 0.14, 0.18, 0.12], [0.42, -0.12, 0.13, 0.17, 0.35]].forEach(function (t) {
      ctx.beginPath(); ctx.ellipse(t[0] * s, t[1] * s, t[2] * s, t[3] * s, t[4], 0, Math.PI * 2); ctx.fill();
    });
    ctx.restore();
  }

  function font(weight, size) { return weight + ' ' + size + 'px ' + FONT; }

  // 文字太長時縮小字級，最小到 minSize
  function fitText(ctx, text, weight, size, maxW, minSize) {
    var s = size;
    ctx.font = font(weight, s);
    while (ctx.measureText(text).width > maxW && s > (minSize || 20)) { s -= 2; ctx.font = font(weight, s); }
    return s;
  }

  // 等字型載入（canvas 不會自動等網路字型）
  function ensureFonts(texts) {
    if (!document.fonts || !document.fonts.load) return Promise.resolve();
    var all = texts.join('');
    return Promise.all(['500', '700', '900'].map(function (w) {
      return document.fonts.load(w + ' 40px "Noto Sans TC"', all).catch(function () {});
    }));
  }

  /**
   * opts:
   *   aspect: '9:16' | '4:5'
   *   photo: HTMLImageElement（可為 null）
   *   focus: {x,y,w,h}（0~1，可為 null）
   *   numbers: [..]，special: [..]
   *   text: { title, info, drawLine, disclaimer: [3 行] }
   *   date：選號日（決定顏色，見 THEMES）；theme：直接指定顏色名稱（測試用）
   * 回傳 Promise<HTMLCanvasElement>
   */
  function render(opts) {
    var size = SIZES[opts.aspect] || SIZES['9:16'];
    var W = size[0], H = size[1], tall = opts.aspect === '9:16';
    var tx = opts.text;
    var C = THEMES[opts.theme] || THEMES[themeName(opts.date)];
    return ensureFonts([tx.title, tx.info, tx.drawLine].concat(tx.disclaimer, '0123456789')).then(function () {
      var cv = document.createElement('canvas'); cv.width = W; cv.height = H;
      var ctx = cv.getContext('2d');
      ctx.textBaseline = 'alphabetic';

      // 外框與腳印花紋
      ctx.fillStyle = C.frame; ctx.fillRect(0, 0, W, H);
      var B = 56, step = 96;
      for (var x = step / 2; x < W; x += step) { paw(ctx, x, B / 2, 22, C.framePaw, 0); paw(ctx, x, H - B / 2, 22, C.framePaw, 0); }
      for (var y = step * 1.5; y < H - step; y += step) { paw(ctx, B / 2, y, 22, C.framePaw, 0); paw(ctx, W - B / 2, y, 22, C.framePaw, 0); }

      // 卡片
      var cx0 = B, cy0 = B, cw = W - 2 * B, chh = H - 2 * B, P = 38;
      ctx.fillStyle = C.card; rr(ctx, cx0, cy0, cw, chh, 40); ctx.fill();
      var L = cx0 + P, R = cx0 + cw - P, IW = R - L;

      // 標題列
      // 4:5：標題、號碼球、文字縮小，把空間讓給照片（照片區接近正方形，捲成一團的貓也放得下）
      // 標題放貓名（使用者 10/24 決定）：字比原本「抽獎號碼」小一點，與卡片邊緣多留空間，在標題列垂直置中
      var titleSize = tall ? 112 : 74, box = tall ? 150 : 96, top = cy0 + P - 6;
      var inset = tall ? 22 : 16;
      ctx.fillStyle = C.pawBox; ctx.strokeStyle = C.line; ctx.lineWidth = 5;
      rr(ctx, R - box, top, box, box, 24); ctx.fill(); ctx.stroke();
      paw(ctx, R - box / 2, top + box / 2 + 4, box * 0.62, C.frame, 0);
      ctx.fillStyle = C.title;
      var ts = fitText(ctx, tx.title, '900', titleSize, IW - box - inset - 36, 40);
      ctx.textBaseline = 'middle';
      ctx.fillText(tx.title, L + inset, top + box / 2 + ts * 0.04);
      ctx.textBaseline = 'alphabetic';
      var y0 = top + box + (tall ? 22 : 16);
      ctx.fillStyle = C.line; ctx.fillRect(L, y0, IW, 4);

      // 下方區塊高度（由下往上排）
      var ballD = tall ? 140 : 104, infoSize = tall ? 40 : 30, lotSize = tall ? 46 : 34;
      // 警語：一行、字小一點；太長會自動縮小到放得下，不換行
      var discSize = tall ? 26 : 21, discLH = discSize * 1.7, gap = tall ? 30 : 16;
      var bottom = cy0 + chh - P + 4;
      var discTop = bottom - discLH * tx.disclaimer.length;
      var div2 = discTop - gap;
      var lotBase = div2 - gap;
      var div1 = lotBase - lotSize - gap;
      var ballsTop = div1 - gap - ballD;
      var infoBase = ballsTop - gap;
      var photoTop = y0 + 4 + gap, photoBottom = infoBase - infoSize - gap;

      // 照片（依自動對焦裁切）
      var ph = photoBottom - photoTop;
      cv.dataset.photoSlot = Math.round(IW) + 'x' + Math.round(ph);
      ctx.save(); rr(ctx, L, photoTop, IW, ph, 28); ctx.clip();
      if (opts.photo) {
        var iw = opts.photo.naturalWidth || opts.photo.width, ih = opts.photo.naturalHeight || opts.photo.height;
        var lay = window.Focus.layout(iw, ih, opts.focus, IW, ph);
        cv.dataset.photoMode = lay.mode;
        if (lay.mode === 'cover') {
          ctx.drawImage(opts.photo, lay.src.x, lay.src.y, lay.src.w, lay.src.h, L, photoTop, IW, ph);
        } else {
          // 背景：同一張照片縮到很小再放大，形成模糊效果（各瀏覽器都支援，不依賴 ctx.filter）
          var bg = window.Focus.cropRect(iw, ih, null, IW / ph);
          var tiny = document.createElement('canvas'); tiny.width = 24; tiny.height = Math.max(1, Math.round(24 * ph / IW));
          var tctx = tiny.getContext('2d'); tctx.imageSmoothingQuality = 'high';
          tctx.drawImage(opts.photo, bg.x, bg.y, bg.w, bg.h, 0, 0, tiny.width, tiny.height);
          ctx.imageSmoothingEnabled = true; ctx.imageSmoothingQuality = 'high';
          ctx.drawImage(tiny, 0, 0, tiny.width, tiny.height, L, photoTop, IW, ph);
          ctx.globalAlpha = 0.28; ctx.fillStyle = C.card; ctx.fillRect(L, photoTop, IW, ph); ctx.globalAlpha = 1;   // 背景稍微淡化，讓主角更突出
          var d = lay.dst;
          ctx.save();
          ctx.shadowColor = 'rgba(58,39,27,0.25)'; ctx.shadowBlur = 24;
          ctx.drawImage(opts.photo, lay.src.x, lay.src.y, lay.src.w, lay.src.h, L + d.x, photoTop + d.y, d.w, d.h);
          ctx.restore();
        }
      } else {
        ctx.fillStyle = C.empty; ctx.fillRect(L, photoTop, IW, ph);
        paw(ctx, L + IW / 2, photoTop + ph / 2, Math.min(IW, ph) * 0.35, C.framePaw, 0);
      }
      ctx.restore();
      ctx.strokeStyle = C.photoStroke; ctx.lineWidth = 5; rr(ctx, L, photoTop, IW, ph, 28); ctx.stroke();

      // 貓名｜抽選日期
      ctx.fillStyle = C.text; ctx.textAlign = 'center';
      fitText(ctx, tx.info, '700', infoSize, IW, 22);
      ctx.fillText(tx.info, L + IW / 2, infoBase);

      // 號碼球
      var balls = (opts.numbers || []).map(function (n) { return { n: n, sp: false }; })
        .concat((opts.special || []).map(function (n) { return { n: n, sp: true }; }));
      var n = balls.length, gapB = (IW - n * ballD) / Math.max(1, n - 1);
      if (gapB > 30) gapB = 30;
      var rowW = n * ballD + (n - 1) * gapB, bx = L + (IW - rowW) / 2;
      // 號碼球位置留給動畫用；hideBalls 時只畫底圖（影片每一格再把球疊上去）
      cv._balls = balls.map(function (b, i) {
        return { n: b.n, sp: b.sp, cx: bx + i * (ballD + gapB) + ballD / 2, cy: ballsTop + ballD / 2, d: ballD };
      });
      cv._theme = C;
      if (!opts.hideBalls) cv._balls.forEach(function (b) { drawBall(ctx, b, C, 1, 0); });

      // 分隔線、開獎資訊、警語
      ctx.fillStyle = C.line; ctx.fillRect(L, div1, IW, 4); ctx.fillRect(L, div2, IW, 4);
      ctx.fillStyle = C.text;
      fitText(ctx, tx.drawLine, '700', lotSize, IW, 24);
      ctx.fillText(tx.drawLine, L + IW / 2, lotBase);
      ctx.font = font('500', discSize);
      tx.disclaimer.forEach(function (line, i) {
        fitText(ctx, line, '500', discSize, IW, 18);
        ctx.fillText(line, L + IW / 2, discTop + discLH * (i + 0.8));
      });
      ctx.textAlign = 'left';
      return cv;
    });
  }

  function drawBall(ctx, b, C, scale, dy) {
    ctx.save();
    ctx.translate(b.cx, b.cy + dy); ctx.scale(scale, scale);
    ctx.fillStyle = b.sp ? C.ballDark : C.ball;
    ctx.beginPath(); ctx.arc(0, 0, b.d / 2, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = C.ballText; ctx.font = font('900', Math.round(b.d * 0.5));
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(String(b.n).padStart(2, '0'), 0, b.d * 0.03);
    ctx.restore();
  }

  // ── 影片：號碼球一顆一顆跳進來 ───────────────────────────
  // 時間軸（毫秒）：開頭停 START，每顆間隔 STEP，每顆落下 DROP，最後停 HOLD
  var ANIM = { START: 400, STEP: 380, DROP: 520, HOLD: 1800 };
  function animLength(nBalls) { return ANIM.START + Math.max(0, nBalls - 1) * ANIM.STEP + ANIM.DROP + ANIM.HOLD; }

  // 落下＋彈跳：p 0→1，回傳 { dy（往上為負，單位為球徑）, scale }
  function bounce(p) {
    if (p <= 0) return null;
    if (p >= 1) return { dy: 0, sc: 1 };
    if (p < 0.55) { var q = p / 0.55; return { dy: -(1 - q * q) * 2.2, sc: 0.9 + 0.1 * q }; }   // 從上方加速落下
    if (p < 0.7) { var r = (p - 0.55) / 0.15; return { dy: 0, sc: 1 + 0.14 * Math.sin(r * Math.PI) }; }  // 落地壓扁回彈
    var u = (p - 0.7) / 0.3; return { dy: -Math.sin(u * Math.PI) * 0.28, sc: 1 };                      // 小彈一下
  }

  // 依時間 t 畫一格：底圖＋已出現的球
  function drawFrame(ctx, base, t) {
    ctx.drawImage(base, 0, 0);
    base._balls.forEach(function (b, i) {
      var p = (t - ANIM.START - i * ANIM.STEP) / ANIM.DROP;
      var f = bounce(p);
      if (!f) return;
      var sc = f.sc;
      ctx.save();
      if (f.dy === 0 && p >= 0.55 && p < 0.7) {   // 壓扁：橫向放大、縱向縮小
        ctx.translate(b.cx, b.cy + b.d / 2); ctx.scale(sc, 2 - sc); ctx.translate(-b.cx, -(b.cy + b.d / 2));
        sc = 1;
      }
      drawBall(ctx, b, base._theme, sc, f.dy * b.d);
      ctx.restore();
    });
  }

  // 可錄影片的格式：優先 MP4（IG、LINE 都吃），沒有才用 WebM
  function videoType() {
    if (!window.MediaRecorder || !HTMLCanvasElement.prototype.captureStream) return null;
    var types = ['video/mp4;codecs=avc1.42E01E', 'video/mp4;codecs=avc1', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
    for (var i = 0; i < types.length; i++) if (MediaRecorder.isTypeSupported(types[i])) return types[i];
    return null;
  }

  /**
   * 錄成影片：opts 與 render 相同，另可傳 canvas（顯示錄製過程用）
   * 回傳 Promise<{ blob, type, ext, ms }>；瀏覽器不支援時 reject
   */
  function renderVideo(opts) {
    var type = videoType();
    if (!type) return Promise.reject(new Error('unsupported'));
    var o = {}; for (var k in opts) o[k] = opts[k];
    o.hideBalls = true;
    return render(o).then(function (base) {
      var cv = opts.canvas || document.createElement('canvas');
      cv.width = base.width; cv.height = base.height;
      var ctx = cv.getContext('2d');
      drawFrame(ctx, base, 0);
      var stream = cv.captureStream(30);
      var rec = new MediaRecorder(stream, { mimeType: type, videoBitsPerSecond: 8000000 });
      var chunks = [];
      rec.ondataavailable = function (e) { if (e.data && e.data.size) chunks.push(e.data); };
      var total = animLength(base._balls.length), t0 = null;
      return new Promise(function (resolve, reject) {
        rec.onstop = function () {
          var mt = type.split(';')[0];
          resolve({ blob: new Blob(chunks, { type: mt }), type: mt, ext: mt === 'video/mp4' ? 'mp4' : 'webm', ms: total });
        };
        rec.onerror = function (e) { reject(e.error || e); };
        rec.start(250);
        function tick(now) {
          if (t0 === null) t0 = now;
          var t = now - t0;
          drawFrame(ctx, base, t);
          if (t < total) requestAnimationFrame(tick); else setTimeout(function () { rec.stop(); }, 120);
        }
        requestAnimationFrame(tick);
      });
    });
  }

  function shareFile(blob, filename, title) {
    var file = new File([blob], filename, { type: blob.type });
    if (navigator.canShare && navigator.canShare({ files: [file] })) {
      return navigator.share({ files: [file], title: title }).then(function () { return 'shared'; },
        function (e) { return e && e.name === 'AbortError' ? 'cancelled' : download(blob, filename); });
    }
    return Promise.resolve(download(blob, filename));
  }

  function toBlob(canvas) {
    return new Promise(function (res) { canvas.toBlob(res, 'image/png'); });
  }

  // 手機：系統分享選單（可直接傳 IG、LINE）；不支援時下載 PNG
  function share(canvas, filename, title) {
    return toBlob(canvas).then(function (blob) {
      var file = new File([blob], filename, { type: 'image/png' });
      if (navigator.canShare && navigator.canShare({ files: [file] })) {
        return navigator.share({ files: [file], title: title }).then(function () { return 'shared'; },
          function (e) { return e && e.name === 'AbortError' ? 'cancelled' : download(blob, filename); });
      }
      return download(blob, filename);
    });
  }

  function download(blob, filename) {
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = filename;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(function () { URL.revokeObjectURL(a.href); }, 5000);
    return 'downloaded';
  }

  window.Card = { render: render, share: share, toBlob: toBlob, SIZES: SIZES, THEMES: THEMES, themeName: themeName,
                  renderVideo: renderVideo, videoType: videoType, drawFrame: drawFrame, animLength: animLength, shareFile: shareFile };
})();
