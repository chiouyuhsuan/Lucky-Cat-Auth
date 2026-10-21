// Firestore 安全規則測試
// 執行：npx firebase emulators:exec --only firestore "node tests/rules.test.mjs"
import { readFileSync } from 'node:fs';
import { initializeTestEnvironment, assertSucceeds, assertFails } from '@firebase/rules-unit-testing';
import { doc, setDoc, updateDoc, deleteDoc, getDoc, addDoc, collection,
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
const newDraw = (uid) => ({
  uid, catId: 'cat1', catName: '胖虎',
  lotType: 'tw', lotName: '台灣大樂透', lotFlag: '🇹🇼',
  numbers: [1, 2, 3, 4, 5, 6], special: [7],
  country: 'Taiwan', countryCode: 'TW', city: 'Taipei', date: '2026.10.21',
  photoThumb: PHOTO, createdAt: serverTimestamp(), prizeLevel: 0, prizeAmount: 0,
});

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

console.log('draws');
await t('登入者可新增自己的選號', () => assertSucceeds(addDoc(collection(alice, 'draws'), newDraw('alice'))));
await t('不能用別人 uid 新增選號', () => assertFails(addDoc(collection(alice, 'draws'), newDraw('bob'))));
await t('不能新增時就標中獎', () => assertFails(addDoc(collection(alice, 'draws'), { ...newDraw('alice'), prizeLevel: 1, prizeAmount: 100000000 })));
await t('不能新增時塞 checkedAt', () => assertFails(addDoc(collection(alice, 'draws'), { ...newDraw('alice'), checkedAt: serverTimestamp() })));
await t('號碼不能超過 6 個', () => assertFails(addDoc(collection(alice, 'draws'), { ...newDraw('alice'), numbers: [1,2,3,4,5,6,7] })));
await t('樂透類型只能 tw/us/jp', () => assertFails(addDoc(collection(alice, 'draws'), { ...newDraw('alice'), lotType: 'xx' })));
await setDoc(doc(alice, 'draws/d1'), newDraw('alice'));
await t('擁有者不能改成中獎', () => assertFails(updateDoc(doc(alice, 'draws/d1'), { prizeLevel: 1 })));
await t('不能刪選號', () => assertFails(deleteDoc(doc(alice, 'draws/d1'))));
await t('任何人可讀選號', () => assertSucceeds(getDoc(doc(guest, 'draws/d1'))));

console.log('stats / draws_results / 其他');
await t('登入者可建立 stats', () => assertSucceeds(setDoc(doc(alice, 'stats/global'), { totalDraws: 1 })));
await t('stats 只能 +1', () => assertSucceeds(updateDoc(doc(alice, 'stats/global'), { totalDraws: increment(1) })));
await t('stats 不能 +100', () => assertFails(updateDoc(doc(alice, 'stats/global'), { totalDraws: increment(100) })));
await t('未登入不能動 stats', () => assertFails(updateDoc(doc(guest, 'stats/global'), { totalDraws: increment(1) })));
await t('前端不能寫開獎結果', () => assertFails(setDoc(doc(alice, 'draws_results/tw_1'), { numbers: [1] })));
await t('任何人可讀開獎結果', () => assertSucceeds(getDoc(doc(guest, 'draws_results/tw_1'))));
await t('未定義的集合一律拒絕', () => assertFails(setDoc(doc(alice, 'hack/x'), { a: 1 })));

await env.cleanup();
console.log(`\n${pass} 通過，${fail} 失敗`);
process.exit(fail ? 1 : 0);
