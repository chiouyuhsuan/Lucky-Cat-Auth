// 排行榜、貓咪牆、關於頁右上角：登入後顯示帳號選單（與首頁一致），未登入維持「開始選號」
// 用法：<div id="nav-right"><a class="nav-cta" href="index.html">開始選號</a></div>
//       <script type="module" src="js/navuser.js"></script>
import { auth } from "./firebase.js";
import { onAuthStateChanged, signOut } from "https://www.gstatic.com/firebasejs/12.12.0/firebase-auth.js";

const TXT = {
  zh: { records: '🐱 我的貓咪紀錄', logout: '登出', user: '用戶' },
  en: { records: '🐱 My cats', logout: 'Log out', user: 'User' },
  ja: { records: '🐱 わたしの猫の記録', logout: 'ログアウト', user: 'ユーザー' },
};
const lang = () => { try { return TXT[localStorage.getItem('lang')] ? localStorage.getItem('lang') : 'zh'; } catch (e) { return 'zh'; } };
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

const box = document.getElementById('nav-right');
const guestHtml = box ? box.innerHTML : '';
let current = null;

function render() {
  if (!box) return;
  const user = current;
  if (!user) {
    box.innerHTML = guestHtml;
    if (window.setLang) { try { window.setLang(lang()); } catch (e) {} }   // 關於頁：按鈕文字跟著語言
    return;
  }
  const t = TXT[lang()];
  const name = user.displayName || (user.email ? user.email.split('@')[0] : t.user);
  const photo = window.Safe ? window.Safe.img(user.photoURL) : (/^https:\/\//.test(user.photoURL || '') ? user.photoURL : '');
  box.innerHTML = '<div class="nav-user-menu" id="nav-user-menu">'
    + (photo ? '<img class="nav-user-photo" src="' + esc(photo) + '" alt="" referrerpolicy="no-referrer"/>'
             : '<div class="nav-user-avatar">' + esc(name.charAt(0).toUpperCase()) + '</div>')
    + '<span class="nav-user-name">' + esc(name) + '</span>'
    + '<span style="font-size:10px;color:#888780;margin-left:2px">▾</span>'
    + '<div class="nav-dropdown" id="nav-dropdown">'
    + '<div class="nav-dropdown-item" data-act="records">' + esc(t.records) + '</div>'
    + '<div class="nav-dropdown-divider"></div>'
    + '<div class="nav-dropdown-item" data-act="logout" style="color:#791F1F">' + esc(t.logout) + '</div>'
    + '</div></div>';
  const img = box.querySelector('.nav-user-photo');
  if (img) img.addEventListener('error', () => { img.style.display = 'none'; });
}

document.addEventListener('click', async e => {
  const menu = document.getElementById('nav-user-menu');
  const dd = document.getElementById('nav-dropdown');
  if (!menu || !dd) return;
  const item = e.target.closest('.nav-dropdown-item');
  if (item && menu.contains(item)) {
    dd.classList.remove('open');
    if (item.dataset.act === 'records') {
      try { sessionStorage.setItem('goto', 'profile'); } catch (err) {}
      location.href = 'index.html';
    } else if (item.dataset.act === 'logout') {
      if (window.LC) window.LC.track('logout');
      await signOut(auth);
    }
    return;
  }
  if (menu.contains(e.target)) dd.classList.toggle('open');
  else dd.classList.remove('open');
});

onAuthStateChanged(auth, user => {
  current = user;
  if (window.LC) window.LC.setUser(user ? user.uid : null);
  render();
});

// 關於頁切換語言時，選單文字跟著換
document.addEventListener('click', e => { if (e.target.closest('.lang-btn')) setTimeout(render, 0); });
