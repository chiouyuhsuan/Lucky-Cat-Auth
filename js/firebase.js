// 共用 Firebase 初始化。所有頁面從這裡取得 app / auth / db，設定只維護一份。
// 注意：Firebase 網頁設定（apiKey 等）本來就會公開在前端，不是密鑰；
// 資料安全靠的是 firestore.rules，不是隱藏這段設定。
import { initializeApp } from "https://www.gstatic.com/firebasejs/12.12.0/firebase-app.js";
import { getAuth } from "https://www.gstatic.com/firebasejs/12.12.0/firebase-auth.js";
import { getFirestore } from "https://www.gstatic.com/firebasejs/12.12.0/firebase-firestore.js";

export const firebaseConfig = {
  apiKey: "AIzaSyAP90Ihnh_ekNcchfPxdX-VuKdGmNDrktE",
  authDomain: "pangfu-pangji.firebaseapp.com",
  projectId: "pangfu-pangji",
  storageBucket: "pangfu-pangji.firebasestorage.app",
  messagingSenderId: "966100033494",
  appId: "1:966100033494:web:b03e4664570ffe9a24ce77"
};

export const app  = initializeApp(firebaseConfig);
export const auth = getAuth(app);
export const db   = getFirestore(app);
