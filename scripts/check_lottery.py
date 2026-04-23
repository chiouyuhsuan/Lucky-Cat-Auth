"""
台灣大樂透開獎核對腳本 v2
- 使用 TaiwanLotteryCrawler 套件直接抓官方開獎號碼（最穩定）
- 備用方案：爬 taiwanlottery.com/lotto/result/lotto649
- 寫入 Firestore draws_results 集合
- 核對本期有效用戶選號，更新中獎狀態
"""

import os
import json
import re
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone

TZ_TW = timezone(timedelta(hours=8))

def now_tw():
    return datetime.now(TZ_TW)

# ── Firebase 初始化 ───────────────────────────────────────
def init_firebase():
    sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if not sa_json:
        raise RuntimeError('FIREBASE_SERVICE_ACCOUNT 未設定')
    cred = credentials.Certificate(json.loads(sa_json))
    firebase_admin.initialize_app(cred)
    return firestore.client()

# ── 方法一：TaiwanLotteryCrawler 套件 ─────────────────────
def fetch_via_crawler():
    """
    用 TaiwanLotteryCrawler 套件抓最新大樂透號碼
    回傳格式範例:
    [{'period': '115000046', 'date': '2026/04/21',
      'numbers': [1,6,17,19,20,40], 'special': 22}]
    """
    try:
        from TaiwanLottery import TaiwanLotteryCrawler
        crawler = TaiwanLotteryCrawler()
        # 取今年今月資料
        today = now_tw()
        data = crawler.lotto649([str(today.year), str(today.month).zfill(2)])
        if not data:
            return None
        # 取最後一筆（最新一期）
        latest = data[-1]
        print(f'[DEBUG] crawler raw: {latest}')
        # 欄位名稱依套件版本可能不同，嘗試多種
        period  = latest.get('period') or latest.get('no') or latest.get('期別') or ''
        date    = latest.get('date')   or latest.get('開獎日期') or today.strftime('%Y/%m/%d')
        nums_raw = (latest.get('number') or latest.get('numbers') or
                    latest.get('獎號') or [])
        sp_raw   = (latest.get('special_number') or latest.get('special') or
                    latest.get('特別號') or 0)
        # 統一格式
        if isinstance(nums_raw, str):
            nums_raw = [int(x) for x in re.findall(r'\d+', nums_raw)]
        if isinstance(sp_raw, (list, tuple)):
            sp_raw = sp_raw[0] if sp_raw else 0
        numbers = sorted([int(n) for n in nums_raw if 1 <= int(n) <= 49])[:6]
        special = int(sp_raw) if sp_raw else 0
        if len(numbers) == 6 and special:
            # 民國年轉西元年
            if isinstance(date, str) and re.match(r'^\d{3}/', date):
                y, rest = date.split('/', 1)
                date = str(int(y) + 1911) + '/' + rest
            return {
                'period': str(period).strip(),
                'date': date,
                'numbers': numbers,
                'special': special,
            }
    except Exception as e:
        print(f'[WARN] TaiwanLotteryCrawler 失敗: {e}')
    return None

# ── 方法二：直接爬台彩官網 lotto649 結果頁 ────────────────
def fetch_via_official_page():
    """
    爬 https://www.taiwanlottery.com/lotto/result/lotto649
    官網頁面結構：期別在 <div class="period_no"> 或 h2
    號碼球在 <div class="ball_tx"> 或 <span class="number">
    """
    url = 'https://www.taiwanlottery.com/lotto/result/lotto649'
    headers = {
        'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                       'AppleWebKit/537.36 Chrome/124.0 Safari/537.36'),
        'Accept-Language': 'zh-TW,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.taiwanlottery.com/',
    }
    try:
        resp = requests.get(url, headers=headers, timeout=20)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'html.parser')
        print(f'[DEBUG] 官網頁面長度: {len(resp.text)} bytes')

        result = {}

        # ── 找期別 ──────────────────────────────────────
        # 新版台彩頁面常見 selector
        period_el = (soup.select_one('.period') or
                     soup.select_one('.ball_period') or
                     soup.select_one('[class*="period"]'))
        if period_el:
            pm = re.search(r'(\d{9})', period_el.get_text())
            if pm:
                result['period'] = pm.group(1)

        if 'period' not in result:
            pm = re.search(r'第\s*(\d{9})\s*期', resp.text)
            if pm:
                result['period'] = pm.group(1)

        # ── 找開獎日期 ──────────────────────────────────
        date_el = (soup.select_one('.date') or
                   soup.select_one('[class*="date"]'))
        if date_el:
            dm = re.search(r'(\d{3})/(\d{2})/(\d{2})', date_el.get_text())
            if dm:
                y = int(dm.group(1)) + 1911
                result['date'] = f'{y}/{dm.group(2)}/{dm.group(3)}'
        if 'date' not in result:
            dm = re.search(r'(\d{3})/(\d{2})/(\d{2})', resp.text)
            if dm:
                y = int(dm.group(1)) + 1911
                result['date'] = f'{y}/{dm.group(2)}/{dm.group(3)}'

        # ── 找號碼球 ────────────────────────────────────
        # 嘗試多種 selector
        ball_els = (soup.select('.ball_tx') or
                    soup.select('.number_ball') or
                    soup.select('[class*="ball"]') or
                    soup.select('[class*="num"]'))

        ball_numbers = []
        for el in ball_els:
            txt = el.get_text(strip=True)
            if re.match(r'^\d{1,2}$', txt):
                n = int(txt)
                if 1 <= n <= 49:
                    ball_numbers.append(n)

        print(f'[DEBUG] 找到號碼球元素數量: {len(ball_numbers)}, 內容: {ball_numbers[:10]}')

        if len(ball_numbers) >= 7:
            result['numbers'] = sorted(ball_numbers[:6])
            result['special'] = ball_numbers[6]
        elif len(ball_numbers) >= 6:
            result['numbers'] = sorted(ball_numbers[:6])
            # 特別號另外找
            sp_el = (soup.select_one('.ball_special') or
                     soup.select_one('[class*="special"]'))
            if sp_el:
                sp_txt = sp_el.get_text(strip=True)
                if re.match(r'^\d{1,2}$', sp_txt):
                    result['special'] = int(sp_txt)

        if result.get('numbers') and result.get('special') and result.get('period'):
            return result

    except Exception as e:
        print(f'[WARN] 官網爬蟲失敗: {e}')
    return None

# ── 方法三：爬 atsunny.tw（備用，準確度較高的第三方）───────
def fetch_via_atsunny():
    """
    atsunny.tw 整合台彩資料，頁面結構較穩定
    """
    url = 'https://atsunny.tw/lotto-649/'
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.encoding = 'utf-8'
        text = resp.text

        # 找期別
        pm = re.search(r'第\s*(\d{9})\s*期', text)
        period = pm.group(1) if pm else ''

        # 找日期（頁面通常有 YYYY/MM/DD 或 民國年）
        dm = re.search(r'(\d{3})/(\d{2})/(\d{2})', text)
        if dm:
            y = int(dm.group(1)) + 1911
            date = f'{y}/{dm.group(2)}/{dm.group(3)}'
        else:
            dm2 = re.search(r'(\d{4})/(\d{2})/(\d{2})', text)
            date = dm2.group(0) if dm2 else now_tw().strftime('%Y/%m/%d')

        # 找最新期號碼 — atsunny 頁面頂部有結構化的號碼
        soup = BeautifulSoup(text, 'html.parser')

        # 找所有數字，取最新一組 6+1
        all_divs = soup.find_all(['span', 'div', 'td'],
                                 class_=re.compile(r'num|ball|number|lotto', re.I))
        nums = []
        seen = set()
        for el in all_divs:
            t = el.get_text(strip=True)
            if re.match(r'^\d{1,2}$', t):
                n = int(t)
                if 1 <= n <= 49 and n not in seen:
                    nums.append(n)
                    seen.add(n)
                    if len(nums) == 7:
                        break

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

# ── 主要爬取函式（依序嘗試三種方法）─────────────────────
def fetch_latest_lotto649():
    print('[INFO] 嘗試方法1: TaiwanLotteryCrawler 套件')
    r = fetch_via_crawler()
    if r and r.get('numbers') and r.get('period'):
        print(f'[INFO] 方法1 成功')
        return r

    print('[INFO] 嘗試方法2: 官網 lotto649 結果頁')
    r = fetch_via_official_page()
    if r and r.get('numbers') and r.get('period'):
        print(f'[INFO] 方法2 成功')
        return r

    print('[INFO] 嘗試方法3: atsunny.tw 備用')
    r = fetch_via_atsunny()
    if r and r.get('numbers') and r.get('period'):
        print(f'[INFO] 方法3 成功')
        return r

    return {}

# ── 中獎判斷（台灣大樂透）────────────────────────────────
PRIZE_TABLE = {
    (6, False): (1, '頭獎'),
    (6, True):  (1, '頭獎'),
    (5, True):  (2, '貳獎'),
    (5, False): (3, '參獎'),
    (4, True):  (4, '肆獎'),
    (4, False): (5, '伍獎'),
    (3, True):  (6, '陸獎'),
    (2, True):  (7, '柒獎'),
}
PRIZE_AMOUNTS = {1:100000000, 2:5000000, 3:200000,
                 4:10000, 5:1000, 6:400, 7:100}

def check_prize(user_numbers, user_special, win_numbers, win_special):
    if not user_numbers or not win_numbers:
        return 0, '未中獎'
    matched_main    = len(set(user_numbers) & set(win_numbers))
    matched_special = (int(user_special) == int(win_special)) if user_special else False
    key = (matched_main, matched_special)
    if key in PRIZE_TABLE:
        lv, desc = PRIZE_TABLE[key]
        return lv, desc
    return 0, '未中獎'

# ── 有效選號時間窗口 ──────────────────────────────────────
def get_valid_window(draw_date_str):
    draw = datetime.strptime(draw_date_str, '%Y/%m/%d').replace(tzinfo=TZ_TW)
    end_dt = draw.replace(hour=20, minute=0, second=0)
    weekday = draw.weekday()  # 1=Tue, 4=Fri
    days_back = 4 if weekday == 1 else 3  # 週二往前4天=上週五; 週五往前3天=週二
    prev = draw - timedelta(days=days_back)
    start_dt = prev.replace(hour=20, minute=31, second=0)
    return start_dt, end_dt

# ── 主程式 ────────────────────────────────────────────────
def main():
    print(f'[INFO] 開始執行 — 台灣時間 {now_tw().strftime("%Y/%m/%d %H:%M:%S")}')

    db = init_firebase()
    print('[INFO] Firebase 連線成功')

    result = fetch_latest_lotto649()
    print(f'[INFO] 爬取結果: {result}')

    if not result.get('numbers') or not result.get('period'):
        print('[ERROR] 無法取得有效開獎號碼，終止')
        return

    period      = result['period']
    draw_date   = result.get('date', now_tw().strftime('%Y/%m/%d'))
    win_numbers = result['numbers']
    win_special = result['special']

    print(f'[INFO] 期別：{period}，日期：{draw_date}')
    print(f'[INFO] 開獎號碼：{win_numbers}，特別號：{win_special}')

    # ── 確認是否已處理過這期 ──────────────────────────────
    result_ref = db.collection('draws_results').document(f'tw_{period}')
    existing = result_ref.get()
    if existing.exists:
        print(f'[INFO] tw_{period} 已存在，更新資料')
    
    result_ref.set({
        'lotType': 'tw', 'lotName': '台灣大樂透',
        'period': period, 'drawDate': draw_date,
        'numbers': win_numbers, 'special': win_special,
        'updatedAt': firestore.SERVER_TIMESTAMP,
    })
    print(f'[INFO] 開獎結果已寫入 Firestore: tw_{period}')

    # ── 有效時間窗口 ──────────────────────────────────────
    start_dt, end_dt = get_valid_window(draw_date)
    print(f'[INFO] 有效選號時間：{start_dt} ~ {end_dt}')

    # ── 核對用戶選號 ──────────────────────────────────────
    docs = (db.collection('draws')
              .where(filter=firestore.FieldFilter('lotType', '==', 'tw'))
              .where(filter=firestore.FieldFilter('prizeLevel', '==', 0))
              .stream())

    checked = won = 0
    for doc in docs:
        data = doc.to_dict()
        created_at = data.get('createdAt')
        if not created_at or not hasattr(created_at, 'seconds'):
            continue
        created_dt = datetime.fromtimestamp(created_at.seconds, tz=TZ_TW)
        if not (start_dt <= created_dt <= end_dt):
            continue

        user_numbers = data.get('numbers', [])
        user_special = data.get('special', [])
        if isinstance(user_special, list):
            user_special = user_special[0] if user_special else None

        prize_level, prize_desc = check_prize(
            user_numbers, user_special, win_numbers, win_special)

        update = {
            'prizeLevel': prize_level,
            'prizeDesc': prize_desc,
            'checkedAt': firestore.SERVER_TIMESTAMP,
            'drawPeriod': period,
            'winNumbers': win_numbers,
            'winSpecial': win_special,
        }
        if prize_level > 0:
            update['prizeAmount'] = PRIZE_AMOUNTS.get(prize_level, 0)
            won += 1
            print(f'[WIN] {data.get("catName")} 中獎！等級={prize_level} {prize_desc}')

        doc.reference.update(update)
        checked += 1

    print(f'[INFO] 核對完成：共 {checked} 筆，中獎 {won} 筆')
    print('[INFO] 腳本執行完畢 ✓')

if __name__ == '__main__':
    main()
