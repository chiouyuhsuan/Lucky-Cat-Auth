// js/focus.js 單元測試（裁切計算與偵測結果整理，不需載入 AI 模型）
import { test } from 'node:test';
import assert from 'node:assert/strict';
globalThis.window = globalThis.window || {};
globalThis.document = globalThis.document || {};
await import('../js/focus.js');
const F = globalThis.window.Focus;
const near = (a, b, eps = 1) => assert.ok(Math.abs(a - b) <= eps, `${a} ≈ ${b}`);

test('沒有對焦資訊：取最大範圍、置中', () => {
  const c = F.cropRect(1000, 2000, null, 1);       // 直式照片裁正方形
  assert.deepEqual([c.w, c.h], [1000, 1000]); near(c.y, 500);
});

test('實際案例：直式照片、貓在下方三分之二（10/21 胖吉&胖福）', () => {
  // AI 偵測結果：607x1080，bbox [13, 282, 590, 703]
  const focus = F.pickFocus([{ class: 'dog', score: 0.76, bbox: [13, 282, 590, 703] }], 607, 1080);
  const c = F.cropRect(607, 1080, focus, 890 / 560);   // 4:5 卡片的照片版位（橫長）
  // 舊做法固定裁上半部（y=0）只會看到窗戶；新做法裁切中心落在貓的中心
  const catCenterY = 282 + 703 / 2;
  near(c.y + c.h / 2, catCenterY, 2);
  assert.ok(c.y > 300, '裁切區應在照片下半部');
});

test('動物很小時放大，但最多到 60%', () => {
  const c = F.cropRect(1000, 1000, { x: 0.45, y: 0.45, w: 0.05, h: 0.05 }, 1);
  near(c.w, 600); near(c.x + c.w / 2, 475);   // 方框中心 = 0.45 + 0.05/2
});

test('裁切不會超出照片邊界', () => {
  const c = F.cropRect(1000, 1000, { x: 0.9, y: 0.9, w: 0.1, h: 0.1 }, 1);
  assert.ok(c.x >= 0 && c.y >= 0 && c.x + c.w <= 1000 + 1e-6 && c.y + c.h <= 1000 + 1e-6);
});

test('兩隻貓：取聯集；低信心與非動物忽略', () => {
  const f = F.pickFocus([
    { class: 'cat', score: 0.9, bbox: [0, 0, 100, 100] },
    { class: 'cat', score: 0.8, bbox: [300, 300, 100, 100] },
    { class: 'cat', score: 0.2, bbox: [900, 900, 50, 50] },
    { class: 'chair', score: 0.99, bbox: [500, 0, 400, 400] },
  ], 1000, 1000);
  assert.deepEqual([f.x, f.y, f.w, f.h], [0, 0, 0.4, 0.4]);
});

test('沒有動物：回傳 null', () => {
  assert.equal(F.pickFocus([{ class: 'person', score: 0.9, bbox: [0, 0, 10, 10] }], 100, 100), null);
  assert.equal(F.pickFocus([], 100, 100), null);
});
