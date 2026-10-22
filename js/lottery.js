// 樂透規則共用模組（一般 <script> 載入，掛在 window.Lottery）
// 後端 scripts/lottery_rules.py 必須維持同樣的開獎日規則。
(function () {
  var LOTS = {
    tw: { flag: '🇹🇼', main: { count: 6, max: 49 }, sp: { count: 0, max: 0 }, tracked: true,
          drawDays: [2, 5] },              // 週二、週五
    us: { flag: '🇺🇸', main: { count: 5, max: 69 }, sp: { count: 1, max: 26 }, tracked: false },
    jp: { flag: '🇯🇵', main: { count: 6, max: 43 }, sp: { count: 0, max: 0 }, tracked: false },
  };

  var CUTOFF_HOUR = 20;           // 開獎日 20:00 停止銷售
  var TW_OFFSET_MS = 8 * 3600e3;  // 台灣固定 UTC+8，無日光節約

  // 不重複隨機選號（使用 crypto，比 Math.random 均勻）
  function randInt(max) {
    var buf = new Uint32Array(1), limit = Math.floor(0x100000000 / max) * max;
    do { crypto.getRandomValues(buf); } while (buf[0] >= limit);
    return (buf[0] % max) + 1;
  }

  function pick(lotKey) {
    var lot = LOTS[lotKey], main = [], sp = [];
    while (main.length < lot.main.count) {
      var n = randInt(lot.main.max);
      if (main.indexOf(n) === -1) main.push(n);
    }
    main.sort(function (a, b) { return a - b; });
    while (sp.length < lot.sp.count) sp.push(randInt(lot.sp.max));
    return { main: main, special: sp };
  }

  // 以台灣時間表示的年月日時（不受使用者電腦時區影響）
  function twParts(date) {
    var t = new Date(date.getTime() + TW_OFFSET_MS);
    return { y: t.getUTCFullYear(), m: t.getUTCMonth(), d: t.getUTCDate(),
             h: t.getUTCHours(), min: t.getUTCMinutes(), wd: t.getUTCDay() };
  }

  // 台灣大樂透：這組號碼會參加哪一天的開獎
  // 規則：開獎日（週二、週五）20:00 前選號算當天，之後算下一次
  // 回傳 'YYYY-MM-DD'；不對獎的樂透回傳 null
  // 注意：春節等特殊期間台彩可能調整開獎日，以後端實際開獎資料為準
  function targetDrawDate(lotKey, now) {
    var lot = LOTS[lotKey];
    if (!lot || !lot.tracked) return null;
    now = now || new Date();
    var p = twParts(now);
    for (var i = 0; i < 8; i++) {
      var day = new Date(Date.UTC(p.y, p.m, p.d + i));
      if (lot.drawDays.indexOf(day.getUTCDay()) === -1) continue;
      if (i === 0 && p.h >= CUTOFF_HOUR) continue;
      return day.toISOString().slice(0, 10);
    }
    return null;
  }

  // 'YYYY-MM-DD' → 顯示用文字，例如 { md: '10/24', wd: 5 }
  function dateLabel(iso) {
    if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null;
    var d = new Date(iso + 'T00:00:00Z');
    return { md: (d.getUTCMonth() + 1) + '/' + d.getUTCDate(), wd: d.getUTCDay() };
  }

  // 'YYYY.MM.DD'（台灣時間），沿用舊資料的 date 欄位格式
  function todayDot(now) {
    var p = twParts(now || new Date());
    return p.y + '.' + String(p.m + 1).padStart(2, '0') + '.' + String(p.d).padStart(2, '0');
  }

  // 「我買了」的截止時間：開獎日台灣時間 20:00（與安全規則相同）
  function purchaseDeadline(iso) {
    if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null;
    var p = iso.split('-').map(Number);
    return new Date(Date.UTC(p[0], p[1] - 1, p[2], CUTOFF_HOUR - 8));
  }

  var TICKET_PRICE = 50;  // 大樂透每注 50 元

  // 統計：貓的命中率（所有要對獎的大樂透）與實際損益（只算標記「我買了」的）
  function summarize(draws) {
    var cat = { draws: 0, checked: 0, wins: 0, prize: 0, bestLevel: 0 };
    var real = { bought: 0, boughtChecked: 0, boughtPending: 0, cost: 0, prize: 0, wins: 0 };
    draws.forEach(function (d) {
      if (d.lotType !== 'tw' || d.tracked === false) return;
      var checked = !!d.checkedAt, lv = Number(d.prizeLevel) || 0, amt = Number(d.prizeAmount) || 0;
      cat.draws++;
      if (checked) {
        cat.checked++;
        if (lv > 0) {
          cat.wins++; cat.prize += amt;
          cat.bestLevel = cat.bestLevel ? Math.min(cat.bestLevel, lv) : lv;
        }
      }
      if (d.purchased === true) {
        real.bought++; real.cost += TICKET_PRICE;
        if (checked) {
          real.boughtChecked++;
          if (lv > 0) { real.wins++; real.prize += amt; }
        } else {
          real.boughtPending++;
        }
      }
    });
    cat.winRate = cat.checked ? cat.wins / cat.checked : 0;
    real.profit = real.prize - real.cost;
    return { cat: cat, real: real };
  }

  window.Lottery = { LOTS: LOTS, pick: pick, targetDrawDate: targetDrawDate,
                     dateLabel: dateLabel, todayDot: todayDot, CUTOFF_HOUR: CUTOFF_HOUR,
                     purchaseDeadline: purchaseDeadline, summarize: summarize, TICKET_PRICE: TICKET_PRICE };
})();
