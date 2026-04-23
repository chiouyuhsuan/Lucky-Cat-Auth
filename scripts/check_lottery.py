"""
台灣大樂透開獎核對腳本 v3
- 方法1: 爬台彩官網 /lotto/result/lotto649
- 方法2: 爬 atsunny.tw 備用
- 寫入 Firestore draws_results
- 核對本期有效用戶選號
"""

import os, json, re, requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone

TZ_TW = timezone(timedelta(hours=8))

def now_tw():
    return datetime.now(TZ_TW)

# ── Firebase ──────────────────────────────────────────────
def init_firebase():
    sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if not sa_json:
        raise RuntimeError('FIREBASE_SERVICE_ACCOUNT 未設定')
    cred = credentials.Certificate(json.loads(sa_json))
    firebase_admin.initialize_app(cred)
    return firestore.client()

# ── 方法1: 台彩官網 lotto649 結果頁 ──────────────────────
def fetch_official():
    url = 'https://www.taiwanlottery.com/lotto/result/lotto649'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'zh-TW,zh;q=0.9',
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')
        text = resp.text
        print(f'[DEBUG] 官網頁面大小: {len(text)} bytes')

        result = {}

        # ── 期別：找第一個 9 位數字 ──
        pm = re.search(r'(\d{9})', text)
        if pm:
            result['period'] = pm.group(1)

        # ── 日期：找民國年 ──
        dm = re.search(r'(\d{3})/(\d{2})/(\d{2})', text)
        if dm:
            y = int(dm.group(1)) + 1911
            result['date'] = f'{y}/{dm.group(2)}/{dm.group(3)}'

        # ── 號碼球：找頁面中所有 ball 相關 class ──
        nums = []
        # 嘗試各種 selector
        selectors = [
            'div.ball_tx', 'span.ball_tx', 
            'div.ball_number', 'span.ball_number',
            '[class*="ball_no"]', '[class*="lotto_ball"]',
            'div.number', 'span.number',
        ]
        for sel in selectors:
            els = soup.select(sel)
            if els:
                print(f'[DEBUG] selector "{sel}" 找到 {len(els)} 個元素')
                for el in els:
                    t = el.get_text(strip=True)
                    if re.match(r'^\d{1,2}$', t):
                        n = int(t)
                        if 1 <= n <= 49:
                            nums.append(n)
                if len(nums) >= 7:
                    break

        # 如果 selector 找不到，用 regex 從整個頁面找連續出現的 1-49 數字
        if len(nums) < 7:
            print('[DEBUG] selector 失敗，改用 regex 掃描頁面')
            # 找頁面中所有出現的 01-49 格式數字（兩位數）
            all_matches = re.findall(r'\b(0[1-9]|[1-3][0-9]|4[0-9])\b', text)
            seen = set()
            for m in all_matches:
                n = int(m)
                if n not in seen:
                    seen.add(n)
                    nums.append(n)
                if len(nums) == 7:
                    break

        print(f'[DEBUG] 找到號碼: {nums}')

        if len(nums) >= 7 and result.get('period'):
            result['numbers'] = sorted(nums[:6])
            result['special'] = nums[6]
            return result

    except Exception as e:
        print(f'[WARN] 官網爬蟲失敗: {e}')
    return None

# ── 方法2: atsunny.tw 備用 ────────────────────────────────
def fetch_atsunny():
    url = 'https://atsunny.tw/lotto-649/'
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')
        text = resp.text

        # 期別
        pm = re.search(r'第\s*(\d{9})\s*期', text)
        period = pm.group(1) if pm else ''

        # 日期
        dm = re.search(r'(\d{3})/(\d{2})/(\d{2})', text)
        if dm:
            y = int(dm.group(1)) + 1911
            date = f'{y}/{dm.group(2)}/{dm.group(3)}'
        else:
            date = now_tw().strftime('%Y/%m/%d')

        # 號碼：找頁面結構化的數字元素
        nums = []
        seen = set()
        for el in soup.find_all(['span','div','td','li'],
                                class_=re.compile(r'num|ball|number|lotto', re.I)):
            t = el.get_text(strip=True)
            if re.match(r'^\d{1,2}$', t):
                n = int(t)
                if 1 <= n <= 49 and n not in seen:
                    nums.append(n)
                    seen.add(n)
                    if len(nums) == 7:
                        break

        print(f'[DEBUG] atsunny 號碼: {nums}, 期別: {period}')

        if len(nums) >= 7 and period:
            return {
                'period': period,
                'date': date,
                'numbers': sorted(nums[:6]),
                'special': nums[6],
            }
    except Exception as e:
        print(f'[WARN] atsunny 失敗: {e}')
    return None

# ── 方法3: lotto.ctbcbank.com（中信銀行官方開獎頁）────────
def fetch_ctbc():
    """
    中國信託銀行彩券結果頁，結構相對穩定
    """
    url = 'https://lotto.ctbcbank.com/result_all.htm'
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        resp.encoding = 'utf-8'
        text = resp.text
        soup = BeautifulSoup(text, 'lxml')
        print(f'[DEBUG] ctbc 頁面大小: {len(text)} bytes')

        # 找大樂透區塊
        result = {}
        # 期別
        pm = re.search(r'(\d{9})', text)
        if pm:
            result['period'] = pm.group(1)

        # 日期
        dm = re.search(r'(\d{3})/(\d{2})/(\d{2})', text)
        if dm:
            y = int(dm.group(1)) + 1911
            result['date'] = f'{y}/{dm.group(2)}/{dm.group(3)}'

        # 號碼
        nums = []
        seen = set()
        for el in soup.find_all(['td', 'span', 'div']):
            t = el.get_text(strip=True)
            if re.match(r'^0?([1-9]|[1-3][0-9]|4[0-9])$', t):
                n = int(t)
                if 1 <= n <= 49 and n not in seen:
                    nums.append(n)
                    seen.add(n)
                    if len(nums) == 7:
                        break

        print(f'[DEBUG] ctbc 號碼: {nums}')
        if len(nums) >= 7 and result.get('period'):
            result['numbers'] = sorted(nums[:6])
            result['special'] = nums[6]
            return result
    except Exception as e:
        print(f'[WARN] ctbc 失敗: {e}')
    return None

def fetch_latest():
    for name, fn in [('台彩官網', fetch_official),
                     ('atsunny', fetch_atsunny),
                     ('ctbc',    fetch_ctbc)]:
        print(f'[INFO] 嘗試: {name}')
        r = fn()
        if r and r.get('numbers') and r.get('period'):
            print(f'[INFO] {name} 成功')
            return r
    return {}

# ── 中獎判斷 ──────────────────────────────────────────────
PRIZE_TABLE = {
    (6, False):(1,'頭獎'), (6, True):(1,'頭獎'),
    (5, True): (2,'貳獎'), (5, False):(3,'參獎'),
    (4, True): (4,'肆獎'), (4, False):(5,'伍獎'),
    (3, True): (6,'陸獎'), (2, True): (7,'柒獎'),
}
PRIZE_AMOUNTS = {1:100000000,2:5000000,3:200000,4:10000,5:1000,6:400,7:100}

def check_prize(user_nums, user_sp, win_nums, win_sp):
    if not user_nums or not win_nums:
        return 0, '未中獎'
    matched = len(set(user_nums) & set(win_nums))
    has_sp  = (int(user_sp) == int(win_sp)) if user_sp else False
    lv, desc = PRIZE_TABLE.get((matched, has_sp), (0, '未中獎'))
    return lv, desc

# ── 有效時間窗口 ──────────────────────────────────────────
def get_valid_window(draw_date_str):
    draw = datetime.strptime(draw_date_str, '%Y/%m/%d').replace(tzinfo=TZ_TW)
    end_dt   = draw.replace(hour=20, minute=0, second=0)
    days_back = 4 if draw.weekday() == 1 else 3  # 週二往前4天，週五往前3天
    start_dt = (draw - timedelta(days=days_back)).replace(hour=20, minute=31, second=0)
    return start_dt, end_dt

# ── 主程式 ────────────────────────────────────────────────
def main():
    print(f'[INFO] 開始執行 {now_tw().strftime("%Y/%m/%d %H:%M:%S")} (台灣時間)')
    db = init_firebase()
    print('[INFO] Firebase 連線成功')

    result = fetch_latest()
    print(f'[INFO] 爬取結果: {result}')

    if not result.get('numbers') or not result.get('period'):
        print('[ERROR] 無法取得開獎號碼，終止')
        return

    period    = result['period']
    draw_date = result.get('date', now_tw().strftime('%Y/%m/%d'))
    win_nums  = result['numbers']
    win_sp    = result['special']

    print(f'[INFO] 期別：{period} | 日期：{draw_date}')
    print(f'[INFO] 開獎：{win_nums} 特別號：{win_sp}')

    # 確認是否正確（與已知最新期比對）
    known_latest = '115000046'
    if period < known_latest:
        print(f'[WARN] 抓到的期別 {period} 比已知最新 {known_latest} 舊！可能抓錯了')

    # 寫入開獎結果
    db.collection('draws_results').document(f'tw_{period}').set({
        'lotType':'tw', 'lotName':'台灣大樂透',
        'period':period, 'drawDate':draw_date,
        'numbers':win_nums, 'special':win_sp,
        'updatedAt': firestore.SERVER_TIMESTAMP,
    })
    print(f'[INFO] 已寫入 Firestore: tw_{period}')

    # 有效時間窗口
    start_dt, end_dt = get_valid_window(draw_date)
    print(f'[INFO] 有效選號時間：{start_dt} ~ {end_dt}')

    # 核對用戶選號
    docs = (db.collection('draws')
              .where(filter=firestore.FieldFilter('lotType','==','tw'))
              .where(filter=firestore.FieldFilter('prizeLevel','==',0))
              .stream())

    checked = won = 0
    for doc in docs:
        data = doc.to_dict()
        ca = data.get('createdAt')
        if not ca or not hasattr(ca,'seconds'):
            continue
        created_dt = datetime.fromtimestamp(ca.seconds, tz=TZ_TW)
        if not (start_dt <= created_dt <= end_dt):
            continue

        u_nums = data.get('numbers', [])
        u_sp   = data.get('special', [])
        if isinstance(u_sp, list):
            u_sp = u_sp[0] if u_sp else None

        lv, desc = check_prize(u_nums, u_sp, win_nums, win_sp)
        update = {
            'prizeLevel': lv, 'prizeDesc': desc,
            'checkedAt': firestore.SERVER_TIMESTAMP,
            'drawPeriod': period,
            'winNumbers': win_nums, 'winSpecial': win_sp,
        }
        if lv > 0:
            update['prizeAmount'] = PRIZE_AMOUNTS.get(lv, 0)
            won += 1
            print(f'[WIN] {data.get("catName")} 中獎 {lv}等 {desc}！')
        doc.reference.update(update)
        checked += 1

    print(f'[INFO] 核對完成：{checked} 筆，中獎 {won} 筆')
    print('[INFO] 完畢 ✓')

if __name__ == '__main__':
    main()
