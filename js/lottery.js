// 樂透規則共用模組（一般 <script> 載入，掛在 window.Lottery）
// 後端 scripts/lottery_rules.py 必須維持同樣的開獎日規則。
(function () {
  var LOTS = {
    tw: { flag: '🇹🇼', main: { count: 6, max: 49 }, sp: { count: 0, max: 0 }, tracked: true,
          drawDays: [2, 5] },              // 週二、週五
    // Powerball：美東時間週一、三、六 22:59 開獎；22:00（美東）後選號算下一期（各州停售時間不同，取 22:00）
    us: { flag: '🇺🇸', main: { count: 5, max: 69 }, sp: { count: 1, max: 26 }, tracked: true,
          drawDays: [1, 3, 6], tz: 'America/New_York', cutoffHour: 22, currency: 'USD' },
    jp: { flag: '🇯🇵', main: { count: 6, max: 43 }, sp: { count: 0, max: 0 }, tracked: false },
  };

  var CUTOFF_HOUR = 20;           // 大樂透：開獎日 20:00 停止銷售
  var TW_OFFSET_MS = 8 * 3600e3;  // 台灣固定 UTC+8，無日光節約
  var USD_TWD = 31;               // 美元換台幣：固定匯率（11/11 決定），獎金與成本都用這個

  // 指定時區的年月日時（美東有日光節約，交給瀏覽器的時區資料處理）
  function zoneParts(date, tz) {
    var f = new Intl.DateTimeFormat('en-US', { timeZone: tz, year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', hourCycle: 'h23' });
    var o = {};
    f.formatToParts(date).forEach(function (x) { o[x.type] = x.value; });
    return { y: +o.year, m: +o.month - 1, d: +o.day, h: +o.hour % 24 };
  }

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
  // Powerball：回傳美國官方開獎日（美東日期）
  function targetDrawDate(lotKey, now) {
    var lot = LOTS[lotKey];
    if (!lot || !lot.tracked) return null;
    now = now || new Date();
    var p = lot.tz ? zoneParts(now, lot.tz) : twParts(now);
    var cutoff = lot.cutoffHour || CUTOFF_HOUR;
    for (var i = 0; i < 8; i++) {
      var day = new Date(Date.UTC(p.y, p.m, p.d + i));
      if (lot.drawDays.indexOf(day.getUTCDay()) === -1) continue;
      if (i === 0 && p.h >= cutoff) continue;
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

  // 「我買了」的截止時間：開獎隔天台灣時間 24:00（與安全規則相同）
  // 大樂透：開獎日 D 的隔天 24:00 → UTC D+1 16:00
  // Powerball：美東 D 晚上開獎＝台灣 D+1 中午，隔天 24:00 → UTC D+2 16:00
  function purchaseDeadline(iso, lotKey) {
    if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null;
    var p = iso.split('-').map(Number);
    return new Date(Date.UTC(p[0], p[1] - 1, p[2] + (lotKey === 'us' ? 2 : 1), 24 - 8));
  }

  var TICKET_PRICE = 50;  // 大樂透每注 50 元
  var TICKET_TWD = { tw: 50, us: 2 * USD_TWD };   // 每注成本（台幣）：Powerball 2 美元

  // 統計：貓的命中率（所有要對獎的大樂透）與實際損益（只算標記「我買了」的）
  // lotKey：要統計哪一種樂透（預設大樂透）；獎金 prizeAmount 一律是台幣
  function summarize(draws, lotKey) {
    lotKey = lotKey || 'tw';
    var cat = { draws: 0, checked: 0, wins: 0, prize: 0, bestLevel: 0 };
    var real = { bought: 0, boughtChecked: 0, boughtPending: 0, cost: 0, prize: 0, wins: 0 };
    draws.forEach(function (d) {
      if (d.lotType !== lotKey || d.tracked === false) return;
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
        real.bought++; real.cost += TICKET_TWD[lotKey] || TICKET_PRICE;
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
                     purchaseDeadline: purchaseDeadline, summarize: summarize, TICKET_PRICE: TICKET_PRICE,
                     TICKET_TWD: TICKET_TWD, USD_TWD: USD_TWD };
})();
