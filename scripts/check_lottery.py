"""
台灣大樂透開獎核對腳本 v4
方法1: taiwanlottery 套件 (PyPI 正確名稱)
方法2: 爬台彩官網 POST API (台彩用 POST 傳回 JSON)
方法3: 爬 atsunny.tw 備用
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

# ── 方法1: taiwanlottery 套件 (pip install taiwanlottery) ─
def fetch_via_package():
    try:
        from TaiwanLottery import TaiwanLotteryCrawler
        crawler = TaiwanLotteryCrawler()
        today = now_tw()
        data = crawler.lotto649([str(today.year), str(today.month).zfill(2)])
        if not data:
            # 試上個月（月初時可能還沒本月資料）
            last_month = today.replace(day=1) - timedelta(days=1)
            data = crawler.lotto649([str(last_month.year), str(last_month.month).zfill(2)])
        if not data:
            return None
        latest = data[-1]
        print(f'[DEBUG] 套件回傳: {latest}')

        # 套件欄位名稱
        period   = str(latest.get('period', '') or latest.get('no', '')).strip()
        date_raw = latest.get('date', '') or latest.get('開獎日期', '')
        nums_raw = latest.get('number', []) or latest.get('numbers', [])
        sp_raw   = latest.get('special_number', 0) or latest.get('special', 0)

        # 民國年轉西元
        if isinstance(date_raw, str) and re.match(r'^\d{3}/', date_raw):
            parts = date_raw.split('/')
            date_raw = str(int(parts[0]) + 1911) + '/' + '/'.join(parts[1:])

        if isinstance(nums_raw, str):
            nums_raw = [int(x) for x in re.findall(r'\d+', nums_raw)]
        if isinstance(sp_raw, list):
            sp_raw = sp_raw[0] if sp_raw else 0

        numbers = sorted([int(n) for n in nums_raw if 1 <= int(n) <= 49])[:6]
        special = int(sp_raw) if sp_raw else 0

        if len(numbers) == 6 and special and period:
            return {'period': period, 'date': str(date_raw), 'numbers': numbers, 'special': special}
    except Exception as e:
        print(f'[WARN] 套件失敗: {e}')
    return None

# ── 方法2: 台彩官網 POST API ──────────────────────────────
def fetch_via_post_api():
    """
    台彩官網用 POST 請求取得開獎資料
    endpoint: https://www.taiwanlottery.com/lotto/result/lotto649
    """
    today = now_tw()
    url = 'https://www.taiwanlottery.com/lotto/result/lotto649'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Content-Type': 'application/x-www-form-urlencoded',
        'Referer': 'https://www.taiwanlottery.com/lotto/result/lotto649',
        'X-Requested-With': 'XMLHttpRequest',
    }
    # 台彩頁面 POST 參數（顯示最新一期）
    payload = {
        'year': str(today.year - 1911),  # 民國年
        'month': str(today.month).zfill(2),
    }
    try:
        resp = requests.post(url, headers=headers, data=payload, timeout=20)
        resp.encoding = 'utf-8'
        text = resp.text
        print(f'[DEBUG] POST API 回應大小: {len(text)} bytes, 狀態: {resp.status_code}')

        # 解析 JSON 格式回應
        if resp.headers.get('Content-Type', '').startswith('application/json'):
            data = resp.json()
            print(f'[DEBUG] JSON 回應: {str(data)[:200]}')
            # 依回應結構取值...

        # 解析 HTML 格式回應
        soup = BeautifulSoup(text, 'lxml')

        result = {}
        # 期別
        pm = re.search(r'第\s*(\d{9})\s*期', text)
        if pm:
            result['period'] = pm.group(1)

        # 日期
        dm = re.search(r'(\d{3})/(\d{2})/(\d{2})', text)
        if dm:
            result['date'] = f'{int(dm.group(1))+1911}/{dm.group(2)}/{dm.group(3)}'

        # 號碼 - 台彩新版頁面的球號在 data-* 屬性或特定 class
        nums = []
        # 嘗試找 data-num 屬性
        for el in soup.find_all(attrs={'data-num': True}):
            n = int(el['data-num'])
            if 1 <= n <= 49:
                nums.append(n)

        # 嘗試找特定 class 的球
        if not nums:
            for cls in ['ball_tx', 'ball', 'num', 'lotto-num']:
                for el in soup.find_all(class_=re.compile(cls, re.I)):
                    t = el.get_text(strip=True)
                    if re.match(r'^\d{1,2}$', t):
                        n = int(t)
                        if 1 <= n <= 49:
                            nums.append(n)
                if len(nums) >= 7:
                    break

        print(f'[DEBUG] POST 找到號碼: {nums}')
        if len(nums) >= 7 and result.get('period'):
            result['numbers'] = sorted(nums[:6])
            result['special'] = nums[6]
            return result

    except Exception as e:
        print(f'[WARN] POST API 失敗: {e}')
    return None

# ── 方法3: atsunny.tw ─────────────────────────────────────
def fetch_via_atsunny():
    url = 'https://atsunny.tw/lotto-649/'
    try:
        resp = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        resp.encoding = 'utf-8'
        soup = BeautifulSoup(resp.text, 'lxml')
        text = resp.text

        # 找最新期別（頁面結構：「最新開獎：大樂透第 XXXXXXXXX 期」）
        pm = re.search(r'大樂透第\s*(\d{9})\s*期', text)
        if not pm:
            pm = re.search(r'第\s*(\d{9})\s*期', text)
        period = pm.group(1) if pm else ''

        # 日期
        dm = re.search(r'(\d{3})/(\d{2})/(\d{2})', text)
        if dm:
            date = f'{int(dm.group(1))+1911}/{dm.group(2)}/{dm.group(3)}'
        else:
            date = now_tw().strftime('%Y/%m/%d')

        # 號碼 - 找頁面上方最新一組號碼
        # atsunny 頁面有結構化的號碼 span
        nums = []
        seen = set()

        # 找含有開獎號碼的主要區塊
        main_content = soup.find('main') or soup.find('article') or soup
        for el in main_content.find_all(['span', 'div', 'td'],
                                        class_=re.compile(r'num|ball|lotto|number', re.I)):
            t = el.get_text(strip=True)
            if re.match(r'^\d{1,2}$', t):
                n = int(t)
                if 1 <= n <= 49 and n not in seen:
                    nums.append(n)
                    seen.add(n)
                    if len(nums) == 7:
                        break

        # 如果找不到，用 regex 找頁面頂部的號碼序列
        if len(nums) < 7:
            # 找類似「40、22、45、07、11、10。特別號：18」的格式
            m = re.search(
                r'開獎號碼[：:]\s*([\d、，,\s]+)[。\.]?\s*特別號[：:]\s*(\d+)',
                text
            )
            if m:
                raw = re.findall(r'\d+', m.group(1))
                sp  = int(m.group(2))
                nums = [int(x) for x in raw if 1 <= int(x) <= 49][:6]
                if len(nums) == 6:
                    return {
                        'period': period,
                        'date': date,
                        'numbers': sorted(nums),
                        'special': sp,
                    }

        print(f'[DEBUG] atsunny 期別: {period}, 號碼: {nums}')
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

def fetch_latest():
    for name, fn in [
        ('taiwanlottery 套件', fetch_via_package),
        ('台彩 POST API',      fetch_via_post_api),
        ('atsunny.tw',         fetch_via_atsunny),
    ]:
        print(f'[INFO] 嘗試: {name}')
        r = fn()
        if r and r.get('numbers') and r.get('period'):
            print(f'[INFO] {name} 成功')
            return r
    return {}

# ── 中獎判斷 ──────────────────────────────────────────────
PRIZE_TABLE = {
    (6,False):(1,'頭獎'),(6,True):(1,'頭獎'),
    (5,True):(2,'貳獎'),(5,False):(3,'參獎'),
    (4,True):(4,'肆獎'),(4,False):(5,'伍獎'),
    (3,True):(6,'陸獎'),(2,True):(7,'柒獎'),
}
PRIZE_AMOUNTS={1:100000000,2:5000000,3:200000,4:10000,5:1000,6:400,7:100}

def check_prize(u_nums, u_sp, w_nums, w_sp):
    if not u_nums or not w_nums: return 0,'未中獎'
    matched = len(set(u_nums)&set(w_nums))
    has_sp  = (int(u_sp)==int(w_sp)) if u_sp else False
    lv,desc = PRIZE_TABLE.get((matched,has_sp),(0,'未中獎'))
    return lv,desc

def get_valid_window(draw_date_str):
    draw = datetime.strptime(draw_date_str,'%Y/%m/%d').replace(tzinfo=TZ_TW)
    end  = draw.replace(hour=20,minute=0,second=0)
    back = 4 if draw.weekday()==1 else 3
    start= (draw-timedelta(days=back)).replace(hour=20,minute=31,second=0)
    return start, end

# ── 主程式 ────────────────────────────────────────────────
def main():
    print(f'[INFO] 開始 {now_tw().strftime("%Y/%m/%d %H:%M:%S")} 台灣時間')
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

    db.collection('draws_results').document(f'tw_{period}').set({
        'lotType':'tw','lotName':'台灣大樂透',
        'period':period,'drawDate':draw_date,
        'numbers':win_nums,'special':win_sp,
        'updatedAt':firestore.SERVER_TIMESTAMP,
    })
    print(f'[INFO] 已寫入 Firestore: tw_{period}')

    start_dt, end_dt = get_valid_window(draw_date)
    print(f'[INFO] 有效時間：{start_dt} ~ {end_dt}')

    docs = (db.collection('draws')
              .where(filter=firestore.FieldFilter('lotType','==','tw'))
              .where(filter=firestore.FieldFilter('prizeLevel','==',0))
              .stream())

    checked = won = 0
    for doc in docs:
        data = doc.to_dict()
        ca = data.get('createdAt')
        if not ca or not hasattr(ca,'seconds'): continue
        ct = datetime.fromtimestamp(ca.seconds,tz=TZ_TW)
        if not (start_dt <= ct <= end_dt): continue

        u_sp = data.get('special',[])
        if isinstance(u_sp,list): u_sp = u_sp[0] if u_sp else None

        lv,desc = check_prize(data.get('numbers',[]),u_sp,win_nums,win_sp)
        upd = {
            'prizeLevel':lv,'prizeDesc':desc,
            'checkedAt':firestore.SERVER_TIMESTAMP,
            'drawPeriod':period,'winNumbers':win_nums,'winSpecial':win_sp,
        }
        if lv>0:
            upd['prizeAmount']=PRIZE_AMOUNTS.get(lv,0)
            won+=1
            print(f'[WIN] {data.get("catName")} 中獎 {lv}等！')
        doc.reference.update(upd)
        checked+=1

    print(f'[INFO] 核對：{checked} 筆，中獎 {won} 筆')
    print('[INFO] 完畢 ✓')

if __name__=='__main__':
    main()
