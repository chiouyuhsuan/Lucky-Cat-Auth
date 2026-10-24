// 分享圖卡（一般 <script> 載入，掛在 window.Card）
// 依使用者提供的模板：橘色腳印外框、米色卡片、大標、貓照、貓名與抽選日期、號碼球、開獎資訊、理性購買警語
// 尺寸：9:16（限時動態）1080×1920、4:5（貼文）1080×1350
(function () {
  var SIZES = { '9:16': [1080, 1920], '4:5': [1080, 1350] };
  var C = {
    frame: '#F6A85C', framePaw: '#FBC98F', card: '#FFF7EA', line: '#F3B36E',
    title: '#3A271B', text: '#4A3426', ball: '#F9C27F', ballDark: '#EF8E3A', ballText: '#2E1F14',
    photoStroke: '#F3B36E', pawBox: '#FFF7EA'
  };
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
   * 回傳 Promise<HTMLCanvasElement>
   */
  function render(opts) {
    var size = SIZES[opts.aspect] || SIZES['9:16'];
    var W = size[0], H = size[1], tall = opts.aspect === '9:16';
    var tx = opts.text;
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
          ctx.fillStyle = 'rgba(255,247,234,0.28)'; ctx.fillRect(L, photoTop, IW, ph);   // 背景稍微淡化，讓主角更突出
          var d = lay.dst;
          ctx.save();
          ctx.shadowColor = 'rgba(58,39,27,0.25)'; ctx.shadowBlur = 24;
          ctx.drawImage(opts.photo, lay.src.x, lay.src.y, lay.src.w, lay.src.h, L + d.x, photoTop + d.y, d.w, d.h);
          ctx.restore();
        }
      } else {
        ctx.fillStyle = '#FBE3C4'; ctx.fillRect(L, photoTop, IW, ph);
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
      balls.forEach(function (b, i) {
        var cxB = bx + i * (ballD + gapB) + ballD / 2, cyB = ballsTop + ballD / 2;
        ctx.fillStyle = b.sp ? C.ballDark : C.ball;
        ctx.beginPath(); ctx.arc(cxB, cyB, ballD / 2, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = C.ballText; ctx.font = font('900', Math.round(ballD * 0.5));
        ctx.textBaseline = 'middle';
        ctx.fillText(String(b.n).padStart(2, '0'), cxB, cyB + ballD * 0.03);
        ctx.textBaseline = 'alphabetic';
      });

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

  window.Card = { render: render, share: share, toBlob: toBlob, SIZES: SIZES };
})();
