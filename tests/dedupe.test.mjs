// js/dedupe.js 單元測試（雜湊與距離；影像解碼在瀏覽器測）
import { test } from 'node:test';
import assert from 'node:assert/strict';
globalThis.window = globalThis.window || {};
await import('../js/dedupe.js');
const D = globalThis.window.Dedupe;
const gradient = (f) => Array.from({ length: 72 }, (_, i) => f(i % 9, Math.floor(i / 9)));

test('同一張照片：距離 0', () => {
  const a = D.hashFromGray(gradient((x, y) => x * 10 + y));
  assert.equal(D.distance(a, a), 0);
});

test('亮度整體改變（重新壓縮、濾鏡）：仍判定相同', () => {
  const a = D.hashFromGray(gradient((x, y) => (x * 7 + y * 3) % 50));
  const b = D.hashFromGray(gradient((x, y) => ((x * 7 + y * 3) % 50) * 0.8 + 20));
  assert.ok(D.distance(a, b) <= D.THRESHOLD);
});

test('構圖不同的照片：判定不同', () => {
  const a = D.hashFromGray(gradient((x) => x));          // 左暗右亮
  const b = D.hashFromGray(gradient((x) => 9 - x));      // 左亮右暗
  assert.ok(D.distance(a, b) > D.THRESHOLD);
});
