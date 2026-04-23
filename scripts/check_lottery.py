"""
台灣大樂透開獎核對腳本
- 爬取台灣彩券官網最新大樂透開獎號碼
- 寫入 Firestore draws_results 集合
- 核對本期有效用戶選號，更新中獎狀態
"""

import os
import json
import requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone

# ── 台灣時區 ──────────────────────────────────────────────
TZ_TW = timezone(timedelta(hours=8))

def now_tw():
    return datetime.now(TZ_TW)

# ── Firebase 初始化 ───────────────────────────────────────
def init_firebase():
    sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if not sa_json:
        raise RuntimeError('FIREBASE_SERVICE_ACCOUNT 環境變數未設定')
    sa_dict = json.loads(sa_json)
    cred = credentials.Certificate(sa_dict)
    firebase_admin.initialize_app(cred)
    return firestore.client()

# ── 爬取台灣彩券最新大樂透號碼 ────────────────────────────
def fetch_latest_lotto649():
    """
    爬取 taiwanlottery.com 最新大樂透開獎號碼
    回傳: {
      'period': '115000045',  # 期別
      'date': '2026/04/25',   # 開獎日期
      'numbers': [7, 10, 22, 40, 45, 11],  # 正選號碼（排序後）
      'special': 18            # 特別號
    }
    """
    url = 'https://www.taiwanlottery.com/lotto/lotto_lastest_result/'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'zh-TW,zh;q=0.9',
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.encoding = 'utf-8'
    soup = BeautifulSoup(resp.text, 'html.parser')

    result = {}

    # 找期別與日期（頁面結構會有這些資訊）
    try:
        # 嘗試找大樂透的區塊
        # 台彩頁面通常用 class 或 id 標示各遊戲
        # 這裡用多個 selector 嘗試，提高穩定性
        
        # 方法1: 找含「大樂透」文字的區塊
        lotto_section = None
        for section in soup.find_all(['div', 'section', 'article']):
            if '大樂透' in section.get_text() and '特別號' in section.get_text():
                lotto_section = section
                break
        
        if not lotto_section:
            raise ValueError('找不到大樂透開獎區塊')

        text = lotto_section.get_text(separator=' ')
        print(f"[DEBUG] 找到區塊文字片段: {text[:200]}")

        # 找期別（格式：第 XXXXXXXXX 期 或 115XXXXXX）
        import re
        period_match = re.search(r'第\s*(\d{9})\s*期', text)
        if period_match:
            result['period'] = period_match.group(1)

        # 找日期（格式：YYYY/MM/DD 或 民國YYY年MM月DD日）
        date_match = re.search(r'(\d{4}/\d{2}/\d{2})', text)
        if date_match:
            result['date'] = date_match.group(1)
        else:
            # 民國年轉換
            roc_match = re.search(r'(\d{3})年(\d{1,2})月(\d{1,2})日', text)
            if roc_match:
                y = int(roc_match.group(1)) + 1911
                m = roc_match.group(2).zfill(2)
                d = roc_match.group(3).zfill(2)
                result['date'] = f'{y}/{m}/{d}'

        # 找號碼球（通常是 span 或 div 帶有特定 class，數字 01-49）
        balls = []
        special = None
        
        # 找所有數字球元素
        all_nums = re.findall(r'\b(0?[1-9]|[1-3][0-9]|4[0-9])\b', text)
        # 過濾出合理的樂透號碼（1-49），取前7個
        valid = []
        seen = set()
        for n in all_nums:
            num = int(n)
            if 1 <= num <= 49 and num not in seen:
                valid.append(num)
                seen.add(num)
                if len(valid) == 7:
                    break
        
        if len(valid) >= 7:
            balls = sorted(valid[:6])
            special = valid[6]
            result['numbers'] = balls
            result['special'] = special
        
    except Exception as e:
        print(f'[WARN] 主要解析失敗: {e}，嘗試備用方法...')
        result = fetch_lotto_fallback()

    print(f'[INFO] 爬取結果: {result}')
    return result


def fetch_lotto_fallback():
    """
    備用方案：爬取 atsunny.tw（整合台彩資料的第三方）
    """
    url = 'https://atsunny.tw/lotto-649/'
    headers = {'User-Agent': 'Mozilla/5.0'}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.encoding = 'utf-8'
    soup = BeautifulSoup(resp.text, 'html.parser')
    
    import re
    text = soup.get_text(separator=' ')
    
    # 找最新期別和號碼
    result = {}
    period_match = re.search(r'第\s*(\d{9})\s*期', text)
    if period_match:
        result['period'] = period_match.group(1)
    
    # 找號碼（取頁面第一組 6+1）
    nums_match = re.findall(r'\b([0-4]?[0-9])\b', text[:2000])
    valid = []
    seen = set()
    for n in nums_match:
        num = int(n)
        if 1 <= num <= 49 and num not in seen:
            valid.append(num)
            seen.add(num)
            if len(valid) == 7:
                break
    
    if len(valid) >= 7:
        result['numbers'] = sorted(valid[:6])
        result['special'] = valid[6]
    
    result['date'] = now_tw().strftime('%Y/%m/%d')
    return result


# ── 中獎判斷邏輯（台灣大樂透）────────────────────────────
PRIZE_TABLE = {
    # (正選中幾個, 有無特別號) -> (等級, 描述)
    (6, False): (1, '頭獎'),
    (6, True):  (1, '頭獎'),   # 含特別號也是頭獎
    (5, True):  (2, '貳獎'),
    (5, False): (3, '參獎'),
    (4, True):  (4, '肆獎'),
    (4, False): (5, '伍獎'),
    (3, True):  (6, '陸獎'),
    (2, True):  (7, '柒獎'),
}

def check_prize(user_numbers, user_special, winning_numbers, winning_special):
    """
    user_numbers: list of int (用戶選的6個號碼)
    user_special: int (用戶選的特別號)
    winning_numbers: list of int (開獎6個號碼)
    winning_special: int (開獎特別號)
    回傳: (prize_level, prize_desc) 或 (0, '未中獎')
    """
    if not user_numbers or not winning_numbers:
        return 0, '未中獎'
    
    user_set    = set(user_numbers)
    winning_set = set(winning_numbers)
    
    matched_main    = len(user_set & winning_set)
    matched_special = (user_special == winning_special) if user_special else False
    
    key = (matched_main, matched_special)
    if key in PRIZE_TABLE:
        level, desc = PRIZE_TABLE[key]
        return level, desc
    
    return 0, '未中獎'


# ── 決定當期有效選號的時間範圍 ───────────────────────────
def get_valid_draw_window(draw_date_str):
    """
    draw_date_str: '2026/04/25'
    回傳: (start_dt, end_dt)
    有效選號範圍：前一期開獎後 到 本期開獎前30分鐘（20:00）
    """
    draw_date = datetime.strptime(draw_date_str, '%Y/%m/%d').replace(tzinfo=TZ_TW)
    
    # 本期截止：開獎日 20:00
    end_dt = draw_date.replace(hour=20, minute=0, second=0)
    
    # 前一期開獎日（週二->前週五，週五->本週二）
    weekday = draw_date.weekday()  # 0=Mon, 1=Tue, 4=Fri
    if weekday == 1:  # 週二 -> 上個週五
        prev_draw = draw_date - timedelta(days=4)
    elif weekday == 4:  # 週五 -> 本週二
        prev_draw = draw_date - timedelta(days=3)
    else:
        prev_draw = draw_date - timedelta(days=3)
    
    # 前一期開獎後（20:31 之後算下一期開始）
    start_dt = prev_draw.replace(hour=20, minute=31, second=0)
    
    return start_dt, end_dt


# ── 主程式 ────────────────────────────────────────────────
def main():
    print(f'[INFO] 開始執行 — 台灣時間 {now_tw().strftime("%Y/%m/%d %H:%M:%S")}')
    
    # 1. 初始化 Firebase
    db = init_firebase()
    print('[INFO] Firebase 連線成功')
    
    # 2. 爬取最新開獎號碼
    result = fetch_latest_lotto649()
    
    if not result.get('numbers') or not result.get('period'):
        print('[ERROR] 無法取得有效開獎號碼，終止')
        return
    
    period      = result['period']
    draw_date   = result.get('date', now_tw().strftime('%Y/%m/%d'))
    win_numbers = result['numbers']
    win_special = result['special']
    
    print(f'[INFO] 期別：{period}，日期：{draw_date}')
    print(f'[INFO] 開獎號碼：{win_numbers}，特別號：{win_special}')
    
    # 3. 把開獎結果存到 Firestore（draws_results 集合）
    result_ref = db.collection('draws_results').document(f'tw_{period}')
    result_ref.set({
        'lotType':    'tw',
        'lotName':    '台灣大樂透',
        'period':     period,
        'drawDate':   draw_date,
        'numbers':    win_numbers,
        'special':    win_special,
        'updatedAt':  firestore.SERVER_TIMESTAMP,
    })
    print(f'[INFO] 開獎結果已寫入 Firestore: tw_{period}')
    
    # 4. 決定有效選號時間窗口
    start_dt, end_dt = get_valid_draw_window(draw_date)
    print(f'[INFO] 有效選號時間：{start_dt} ~ {end_dt}')
    
    # 5. 查詢所有在時間窗口內且屬於大樂透的 draws
    draws_ref = db.collection('draws')
    query = (draws_ref
             .where('lotType', '==', 'tw')
             .where('prizeLevel', '==', 0))  # 只核對還沒結果的
    
    docs = query.stream()
    checked = 0
    won = 0
    
    for doc in docs:
        data = doc.to_dict()
        
        # 檢查 createdAt 是否在有效時間窗口內
        created_at = data.get('createdAt')
        if created_at is None:
            continue
        
        # Firestore timestamp -> datetime
        if hasattr(created_at, 'seconds'):
            created_dt = datetime.fromtimestamp(created_at.seconds, tz=TZ_TW)
        else:
            continue
        
        if not (start_dt <= created_dt <= end_dt):
            continue  # 不在本期有效範圍內
        
        # 核對號碼
        user_numbers = data.get('numbers', [])
        user_special = data.get('special', [])
        if isinstance(user_special, list):
            user_special = user_special[0] if user_special else None
        
        prize_level, prize_desc = check_prize(
            user_numbers, user_special,
            win_numbers, win_special
        )
        
        # 更新紀錄（不管有沒有中獎都更新，標記已核對）
        update_data = {
            'prizeLevel':  prize_level,
            'prizeDesc':   prize_desc,
            'checkedAt':   firestore.SERVER_TIMESTAMP,
            'drawPeriod':  period,
            'winNumbers':  win_numbers,
            'winSpecial':  win_special,
        }
        
        if prize_level > 0:
            # 中獎了！設定一個示意金額（實際金額需手動更新或接官方公告）
            prize_amounts = {1: 100000000, 2: 5000000, 3: 200000,
                             4: 10000, 5: 1000, 6: 400, 7: 100}
            update_data['prizeAmount'] = prize_amounts.get(prize_level, 0)
            won += 1
            print(f'[WIN] doc={doc.id}, user={data.get("catName")}, '
                  f'等級={prize_level} {prize_desc}')
        
        doc.reference.update(update_data)
        checked += 1
    
    print(f'[INFO] 核對完成：共 {checked} 筆，中獎 {won} 筆')
    print('[INFO] 腳本執行完畢 ✓')


if __name__ == '__main__':
    main()
