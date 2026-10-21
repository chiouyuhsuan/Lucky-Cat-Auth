// Firestore 安全規則測試
// 執行：npx firebase emulators:exec --only firestore "node tests/rules.test.mjs"
import { readFileSync } from 'node:fs';
import { initializeTestEnvironment, assertSucceeds, assertFails } from '@firebase/rules-unit-testing';
import { doc, setDoc, updateDoc, deleteDoc, getDoc, collection, writeBatch,
         serverTimestamp, increment } from 'firebase/firestore';

const env = await initializeTestEnvironment({
  projectId: 'demo-luckycat',
  firestore: { rules: readFileSync(new URL('../firestore.rules', import.meta.url), 'utf8') },
});

const alice = env.authenticatedContext('alice').firestore();
const bob   = env.authenticatedContext('bob').firestore();
const guest = env.unauthenticatedContext().firestore();
const PHOTO = 'data:image/jpeg;base64,AAAA';

const newCat = (uid) => ({
  uid, catName: '胖虎', photoThumb: PHOTO,
  country: 'Taiwan', countryCode: 'TW', city: 'Taipei',
  totalDraws: 1, totalWins: 0, totalPrize: 0,
  createdAt: serverTimestamp(), lastDrawAt: serverTimestamp(),
});
const newDraw = (uid, over = {}) => ({
  schema: 2, uid, catId: 'cat1', catName: '胖虎',
  lotType: 'tw', lotName: '台灣大樂透', lotFlag: '🇹🇼',
  numbers: [1, 2, 3, 4, 5, 6], special: [], targetDrawDate: '2026-10-23', tracked: true, purchased: false,
  country: 'Taiwan', countryCode: 'TW', city: 'Taipei', date: '2026.10.21',
  photoThumb: PHOTO, createdAt: serverTimestamp(), prizeLevel: 0, prizeAmount: 0, ...over,
});
const CARD = 'data:image/jpeg;base64,BBBB';
let seq = 0;
// 模擬前端：同一個 batch 寫選號＋大圖（貓 cat1 已存在時更新它）
function saveBatch(db, draw, { photo = { uid: draw.uid, data: CARD }, withPhoto = true, catUpdate = true } = {}) {
  const b = writeBatch(db);
  const id = 'd' + (++seq);
  if (catUpdate) b.update(doc(db, 'cats', draw.catId), { photoThumb: PHOTO, totalDraws: increment(1), lastDrawAt: serverTimestamp() });
  b.set(doc(db, 'draws', id), draw);
  if (withPhoto) b.set(doc(db, 'photos', id), photo);
  return b.commit();
}

let pass = 0, fail = 0;
async function t(name, fn) {
  try { await fn(); pass++; console.log('  ✓ ' + name); }
  catch (e) { fail++; console.log('  ✗ ' + name + '\n    ' + e.message); }
}

console.log('cats');
await t('登入者可建立自己的貓', () => assertSucceeds(setDoc(doc(alice, 'cats/cat1'), newCat('alice'))));
await t('不能用別人的 uid 建貓', () => assertFails(setDoc(doc(alice, 'cats/x'), newCat('bob'))));
await t('未登入不能建貓', () => assertFails(setDoc(doc(guest, 'cats/y'), newCat('alice'))));
await t('建貓時不能偽造中獎次數', () => assertFails(setDoc(doc(alice, 'cats/z'), { ...newCat('alice'), totalWins: 99 })));
await t('建貓時不能塞多餘欄位', () => assertFails(setDoc(doc(alice, 'cats/z'), { ...newCat('alice'), admin: true })));
await t('貓名不能超過 20 字', () => assertFails(setDoc(doc(alice, 'cats/z'), { ...newCat('alice'), catName: 'x'.repeat(21) })));
await t('照片必須是 data:image', () => assertFails(setDoc(doc(alice, 'cats/z'), { ...newCat('alice'), photoThumb: 'javascript:alert(1)' })));
await t('擁有者可換照片並 +1 次數', () => assertSucceeds(updateDoc(doc(alice, 'cats/cat1'),
  { photoThumb: PHOTO, totalDraws: increment(1), lastDrawAt: serverTimestamp() })));
await t('擁有者不能改中獎金額', () => assertFails(updateDoc(doc(alice, 'cats/cat1'), { totalPrize: 100000000 })));
await t('擁有者不能一次加 10 次', () => assertFails(updateDoc(doc(alice, 'cats/cat1'),
  { totalDraws: increment(10), lastDrawAt: serverTimestamp() })));
await t('別人不能改我的貓', () => assertFails(updateDoc(doc(bob, 'cats/cat1'),
  { photoThumb: PHOTO, totalDraws: increment(1), lastDrawAt: serverTimestamp() })));
await t('不能刪貓', () => assertFails(deleteDoc(doc(alice, 'cats/cat1'))));
await t('任何人可讀貓', () => assertSucceeds(getDoc(doc(guest, 'cats/cat1'))));

console.log('draws（新格式）');
await t('大樂透：6 碼、無特別號、有開獎日 → 可存', () => assertSucceeds(saveBatch(alice, newDraw('alice'))));
await t('不更新貓也可以存（貓已存在）', () => assertSucceeds(saveBatch(alice, newDraw('alice'), { catUpdate: false })));
await t('同一個 batch 新建貓＋選號', async () => {
  const b = writeBatch(alice);
  b.set(doc(alice, 'cats/catNew'), newCat('alice'));
  b.set(doc(alice, 'draws/dNew'), newDraw('alice', { catId: 'catNew' }));
  b.set(doc(alice, 'photos/dNew'), { uid: 'alice', data: CARD });
  await assertSucceeds(b.commit());
});
await t('大樂透不能有特別號（舊規則）', () => assertFails(saveBatch(alice, newDraw('alice', { special: [7] }))));
await t('大樂透不能只有 5 碼', () => assertFails(saveBatch(alice, newDraw('alice', { numbers: [1,2,3,4,5] }))));
await t('大樂透號碼不能重複', () => assertFails(saveBatch(alice, newDraw('alice', { numbers: [1,1,3,4,5,6] }))));
await t('大樂透號碼不能超過 49', () => assertFails(saveBatch(alice, newDraw('alice', { numbers: [1,2,3,4,5,50] }))));
await t('號碼不能是文字', () => assertFails(saveBatch(alice, newDraw('alice', { numbers: ['1',2,3,4,5,6] }))));
await t('大樂透一定要有開獎日', () => assertFails(saveBatch(alice, newDraw('alice', { targetDrawDate: null }))));
await t('開獎日格式要對', () => assertFails(saveBatch(alice, newDraw('alice', { targetDrawDate: '<script>' }))));
await t('Powerball 5+1 可存', () => assertSucceeds(saveBatch(alice, newDraw('alice', { lotType: 'us', numbers: [1,2,3,4,69], special: [26], tracked: false, targetDrawDate: null }))));
await t('Powerball 特別號不能超過 26', () => assertFails(saveBatch(alice, newDraw('alice', { lotType: 'us', numbers: [1,2,3,4,5], special: [27], tracked: false, targetDrawDate: null }))));
await t('Loto6 6 碼可存', () => assertSucceeds(saveBatch(alice, newDraw('alice', { lotType: 'jp', numbers: [1,2,3,4,5,43], tracked: false, targetDrawDate: null }))));
await t('美日不能標成要對獎', () => assertFails(saveBatch(alice, newDraw('alice', { lotType: 'jp', tracked: true, targetDrawDate: null }))));
await t('不能新增時就標中獎', () => assertFails(saveBatch(alice, newDraw('alice', { prizeLevel: 1, prizeAmount: 100000000 }))));
await t('不能新增時就標已購買', () => assertFails(saveBatch(alice, newDraw('alice', { purchased: true }))));
await t('不能新增時塞 checkedAt', () => assertFails(saveBatch(alice, newDraw('alice', { checkedAt: serverTimestamp() }))));
await t('不能用別人 uid', () => assertFails(saveBatch(alice, newDraw('bob'), { catUpdate: false })));
await t('不能掛在別人的貓底下', async () => {
  await env.withSecurityRulesDisabled(c => setDoc(doc(c.firestore(), 'cats/bobcat'), { ...newCat('bob'), createdAt: 1, lastDrawAt: 1 }));
  await assertFails(saveBatch(alice, newDraw('alice', { catId: 'bobcat' }), { catUpdate: false }));
});
await t('不能掛在不存在的貓底下', () => assertFails(saveBatch(alice, newDraw('alice', { catId: 'ghost' }), { catUpdate: false })));
await t('舊格式（沒有 schema）不能再寫入', () => assertFails(saveBatch(alice, (({schema, ...r}) => r)(newDraw('alice')))));
await setDoc(doc(alice, 'draws/fixed'), newDraw('alice'));
await t('擁有者不能改成中獎', () => assertFails(updateDoc(doc(alice, 'draws/fixed'), { prizeLevel: 1 })));
console.log('我買了');
await setDoc(doc(alice, 'draws/future'), newDraw('alice', { targetDrawDate: '2099-12-31' }));
await setDoc(doc(alice, 'draws/past'), newDraw('alice', { targetDrawDate: '2020-01-03' }));
await t('開獎前可標記已買', () => assertSucceeds(updateDoc(doc(alice, 'draws/future'), { purchased: true, purchasedAt: serverTimestamp() })));
await t('開獎前可取消已買', () => assertSucceeds(updateDoc(doc(alice, 'draws/future'), { purchased: false, purchasedAt: serverTimestamp() })));
await t('開獎日 20:00 之後不能改', () => assertFails(updateDoc(doc(alice, 'draws/past'), { purchased: true, purchasedAt: serverTimestamp() })));
await t('別人不能幫我標記', () => assertFails(updateDoc(doc(bob, 'draws/future'), { purchased: true, purchasedAt: serverTimestamp() })));
await t('不能順便改號碼', () => assertFails(updateDoc(doc(alice, 'draws/future'), { purchased: true, purchasedAt: serverTimestamp(), numbers: [1,2,3,4,5,7] })));
await t('不能順便改中獎', () => assertFails(updateDoc(doc(alice, 'draws/future'), { purchased: true, purchasedAt: serverTimestamp(), prizeLevel: 1 })));
await t('purchased 必須是 true/false', () => assertFails(updateDoc(doc(alice, 'draws/future'), { purchased: 'yes', purchasedAt: serverTimestamp() })));
await t('purchasedAt 必須是伺服器時間', () => assertFails(updateDoc(doc(alice, 'draws/future'), { purchased: true, purchasedAt: new Date('2099-01-01') })));
await env.withSecurityRulesDisabled(c => setDoc(doc(c.firestore(), 'draws/checked'), { ...newDraw('alice', { targetDrawDate: '2099-12-31' }), createdAt: 1, checkedAt: 1 }));
await t('已對獎的不能改', () => assertFails(updateDoc(doc(alice, 'draws/checked'), { purchased: true, purchasedAt: serverTimestamp() })));
await setDoc(doc(alice, 'draws/jp'), newDraw('alice', { lotType: 'jp', tracked: false, targetDrawDate: null }));
await t('不對獎的美日樂透不能標記', () => assertFails(updateDoc(doc(alice, 'draws/jp'), { purchased: true, purchasedAt: serverTimestamp() })));
await env.withSecurityRulesDisabled(c => setDoc(doc(c.firestore(), 'draws/legacy'), { uid: 'alice', lotType: 'tw', numbers: [1,2,3,4,5,6], special: [7], createdAt: 1 }));
await t('舊格式紀錄不能標記', () => assertFails(updateDoc(doc(alice, 'draws/legacy'), { purchased: true, purchasedAt: serverTimestamp() })));
await t('不能刪選號', () => assertFails(deleteDoc(doc(alice, 'draws/fixed'))));
await t('任何人可讀選號', () => assertSucceeds(getDoc(doc(guest, 'draws/fixed'))));

console.log('photos（圖卡大圖）');
await t('大圖不能單獨新增（沒有對應選號）', () => assertFails(setDoc(doc(alice, 'photos/lonely'), { uid: 'alice', data: CARD })));
await t('不能替已存在的選號補大圖', () => assertFails(setDoc(doc(alice, 'photos/fixed'), { uid: 'alice', data: CARD })));
await t('大圖 uid 要是自己', () => assertFails(saveBatch(alice, newDraw('alice'), { photo: { uid: 'bob', data: CARD } })));
await t('大圖必須是 JPEG data URL', () => assertFails(saveBatch(alice, newDraw('alice'), { photo: { uid: 'alice', data: 'https://evil.example/x.jpg' } })));
await t('大圖不能超過 900KB', () => assertFails(saveBatch(alice, newDraw('alice'), { photo: { uid: 'alice', data: 'data:image/jpeg;base64,' + 'A'.repeat(900000) } })));
await t('大圖不能修改', () => assertFails(updateDoc(doc(alice, 'photos/d1'), { data: CARD })));
await t('大圖不能刪除', () => assertFails(deleteDoc(doc(alice, 'photos/d1'))));
await t('任何人可讀大圖', () => assertSucceeds(getDoc(doc(guest, 'photos/d1'))));

console.log('stats / draws_results / 其他');
await t('前端不能再寫 stats', () => assertFails(setDoc(doc(alice, 'stats/global'), { totalDraws: 1 })));
await t('任何人可讀 stats', () => assertSucceeds(getDoc(doc(guest, 'stats/global'))));
await t('前端不能寫開獎結果', () => assertFails(setDoc(doc(alice, 'draws_results/tw_1'), { numbers: [1] })));
await t('任何人可讀開獎結果', () => assertSucceeds(getDoc(doc(guest, 'draws_results/tw_1'))));
await t('未定義的集合一律拒絕', () => assertFails(setDoc(doc(alice, 'hack/x'), { a: 1 })));

await env.cleanup();
console.log(`\n${pass} 通過，${fail} 失敗`);
process.exit(fail ? 1 : 0);
