// js/lottery.js 單元測試：node --test tests/
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { webcrypto } from 'node:crypto';
globalThis.window = {};
if (!globalThis.crypto) globalThis.crypto = webcrypto;
await import('../js/lottery.js');
const L = globalThis.window.Lottery;
const tw = s => new Date(s + '+08:00');

test('開獎日：20:00 為界、跨週、跨年', () => {
  assert.equal(L.targetDrawDate('tw', tw('2026-10-20T19:59:59')), '2026-10-20');
  assert.equal(L.targetDrawDate('tw', tw('2026-10-20T20:00:00')), '2026-10-23');
  assert.equal(L.targetDrawDate('tw', tw('2026-10-24T00:10:00')), '2026-10-27');
  assert.equal(L.targetDrawDate('tw', tw('2026-12-30T21:00:00')), '2027-01-01');
  assert.equal(L.targetDrawDate('us', new Date()), null);
});

test('我買了截止時間 = 開獎日台灣時間 20:00', () => {
  assert.equal(L.purchaseDeadline('2026-10-23').toISOString(), '2026-10-23T12:00:00.000Z');
  assert.equal(L.purchaseDeadline(null), null);
  assert.equal(L.purchaseDeadline('<x>'), null);
});

test('選號：數量、範圍、不重複', () => {
  for (let i = 0; i < 5000; i++) {
    const t = L.pick('tw'); assert.equal(new Set(t.main).size, 6); assert.equal(t.special.length, 0);
    assert.ok(t.main.every(n => n >= 1 && n <= 49));
    const u = L.pick('us'); assert.equal(u.main.length, 5); assert.equal(u.special.length, 1);
    assert.ok(u.special[0] >= 1 && u.special[0] <= 26);
  }
});

test('統計：貓的命中率與實際損益分開算', () => {
  const ts = { toMillis: () => 1 };
  const draws = [
    { lotType: 'tw', tracked: true, checkedAt: ts, prizeLevel: 8, prizeAmount: 400, purchased: true },
    { lotType: 'tw', tracked: true, checkedAt: ts, prizeLevel: 0, prizeAmount: 0, purchased: true },
    { lotType: 'tw', tracked: true, checkedAt: ts, prizeLevel: 5, prizeAmount: 2000, purchased: false },
    { lotType: 'tw', tracked: true, purchased: true },                       // 已買、待開獎
    { lotType: 'tw', checkedAt: ts, prizeLevel: 0, special: [7] },            // 舊紀錄：無 tracked、購買未知
    { lotType: 'jp', tracked: false, purchased: false },                      // 不計
  ];
  const s = L.summarize(draws);
  assert.deepEqual(
    { d: s.cat.draws, c: s.cat.checked, w: s.cat.wins, p: s.cat.prize, best: s.cat.bestLevel },
    { d: 5, c: 4, w: 2, p: 2400, best: 5 });
  assert.equal(s.cat.winRate, 0.5);
  assert.deepEqual(
    { b: s.real.bought, pend: s.real.boughtPending, cost: s.real.cost, won: s.real.prize, profit: s.real.profit },
    { b: 3, pend: 1, cost: 150, won: 400, profit: 250 });
});

test('統計：沒有資料時不會除以零', () => {
  const s = L.summarize([]);
  assert.equal(s.cat.winRate, 0); assert.equal(s.real.profit, 0);
});
