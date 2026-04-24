"""
台灣大樂透開獎核對腳本 v7
- 開獎號碼：taiwanlottery 套件 / atsunny.tw 備用
- 各等獎金：Playwright 抓 lottolyzer（結構穩定，中文介面）
- 固定獎金：伍獎$2000 / 陸獎$1000 / 柒獎$400 / 八獎$400
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

# ── 開獎號碼：方法1 taiwanlottery 套件 ───────────────────
def fetch_via_package():
    try:
        from TaiwanLottery import TaiwanLotteryCrawler
        crawler = TaiwanLotteryCrawler()
        today = now_tw()
        data = crawler.lotto649([str(today.year), str(today.month).zfill(2)])
        if not data:
            last = today.replace(day=1) - timedelta(days=1)
            data = crawler.lotto649([str(last.year), str(last.month).zfill(2)])
        if not data: return None
        latest = data[-1]
        print(f'[DEBUG] 套件: {latest}')
        period   = str(latest.get('period','') or latest.get('no','')).strip()
        date_raw = latest.get('date','') or latest.get('開獎日期','')
        nums_raw = latest.get('number',[]) or latest.get('numbers',[])
        sp_raw   = latest.get('special_number',0) or latest.get('special',0)
        if isinstance(date_raw,str) and re.match(r'^\d{3}/',date_raw):
            p=date_raw.split('/'); date_raw=str(int(p[0])+1911)+'/'+'/'.join(p[1:])
        if isinstance(nums_raw,str): nums_raw=[int(x) for x in re.findall(r'\d+',nums_raw)]
        if isinstance(sp_raw,list): sp_raw=sp_raw[0] if sp_raw else 0
        numbers=sorted([int(n) for n in nums_raw if 1<=int(n)<=49])[:6]
        special=int(sp_raw) if sp_raw else 0
        if len(numbers)==6 and special and period:
            return {'period':period,'date':str(date_raw),'numbers':numbers,'special':special}
    except Exception as e:
        print(f'[WARN] 套件失敗: {e}')
    return None

# ── 開獎號碼：方法2 atsunny.tw ────────────────────────────
def fetch_via_atsunny():
    try:
        resp=requests.get('https://atsunny.tw/lotto-649/',
                          headers={'User-Agent':'Mozilla/5.0'},timeout=15)
        resp.encoding='utf-8'; soup=BeautifulSoup(resp.text,'lxml'); text=resp.text
        pm=re.search(r'大樂透第\s*(\d{9})\s*期',text) or re.search(r'第\s*(\d{9})\s*期',text)
        period=pm.group(1) if pm else ''
        dm=re.search(r'(\d{3})/(\d{2})/(\d{2})',text)
        date=f'{int(dm.group(1))+1911}/{dm.group(2)}/{dm.group(3)}' if dm else now_tw().strftime('%Y/%m/%d')
        m=re.search(r'開獎號碼[：:]\s*([\d、，,\s]+)[。\.]?\s*特別號[：:]\s*(\d+)',text)
        if m:
            raw=[int(x) for x in re.findall(r'\d+',m.group(1)) if 1<=int(x)<=49][:6]
            if len(raw)==6 and period:
                return {'period':period,'date':date,'numbers':sorted(raw),'special':int(m.group(2))}
        nums=[]; seen=set()
        for el in (soup.find('main') or soup).find_all(
                ['span','div','td'],class_=re.compile(r'num|ball|lotto|number',re.I)):
            t=el.get_text(strip=True)
            if re.match(r'^\d{1,2}$',t):
                n=int(t)
                if 1<=n<=49 and n not in seen:
                    nums.append(n); seen.add(n)
                    if len(nums)==7: break
        if len(nums)>=7 and period:
            return {'period':period,'date':date,'numbers':sorted(nums[:6]),'special':nums[6]}
    except Exception as e:
        print(f'[WARN] atsunny 失敗: {e}')
    return None

def fetch_latest():
    for name,fn in [('taiwanlottery套件',fetch_via_package),
                    ('atsunny.tw',fetch_via_atsunny)]:
        print(f'[INFO] 嘗試號碼來源: {name}')
        r=fn()
        if r and r.get('numbers') and r.get('period'):
            print(f'[INFO] {name} 成功'); return r
    return {}

# ── 各等獎金：Playwright 抓 lottolyzer ───────────────────
# 固定獎金（台彩規定，永遠不變）
FIXED_AMOUNTS = {5: 2000, 6: 1000, 7: 400, 8: 400}

def fetch_prize_amounts_lottolyzer(period):
    """
    用 Playwright 開 lottolyzer 特定期別頁面
    URL: https://zh.lottolyzer.com/home/taiwan/lotto-649/summary-view/draw/{period}
    抓取獎金表格中的「每人各分 $X」金額
    """
    amounts = dict(FIXED_AMOUNTS)
    # 動態獎項預設值（若抓失敗才用）
    amounts.update({1:100000000, 2:2000000, 3:80000, 4:16000})

    url = f'https://zh.lottolyzer.com/home/taiwan/lotto-649/summary-view/draw/{period}'
    print(f'[INFO] Playwright 開啟: {url}')

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_extra_http_headers({
                'Accept-Language': 'zh-TW,zh;q=0.9',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            page.goto(url, wait_until='networkidle', timeout=30000)

            # 等待獎金表格出現
            try:
                page.wait_for_selector('table', timeout=15000)
                print('[INFO] 找到表格')
            except:
                print('[WARN] 等待表格逾時，嘗試繼續解析')

            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, 'lxml')
        print(f'[DEBUG] 頁面大小: {len(html)} bytes')

        # lottolyzer 中文版獎項名稱對應
        prize_map = {
            '頭獎':1, '壹獎':1, '一獎':1,
            '二獎':2, '貳獎':2,
            '三獎':3, '參獎':3,
            '四獎':4, '肆獎':4,
            '五獎':5, '伍獎':5,
            '六獎':6, '陸獎':6,
            '七獎':7, '柒獎':7,
            '八獎':8, '捌獎':8, '普獎':8,
        }

        # 找獎金表格
        for table in soup.find_all('table'):
            rows = table.find_all('tr')
            for row in rows:
                cells = [td.get_text(strip=True) for td in row.find_all(['td','th'])]
                if len(cells) < 2: continue

                # 找獎項名稱
                level = None
                for cell in cells[:2]:
                    for name, lv in prize_map.items():
                        if name in cell:
                            level = lv
                            break
                    if level: break
                if level is None: continue

                # lottolyzer 欄位：獎項 | 獎金總額 | 中獎注數 | 每人各分
                # 格式範例：「2名中獎每人各分 $1,944,756」或最後一欄純數字
                per_person = 0

                # 優先找含「每人各分」的格子
                for cell in cells:
                    if '每人各分' in cell or '每人' in cell:
                        m = re.search(r'\$?([\d,]+)$', cell.strip())
                        if m:
                            val = int(m.group(1).replace(',',''))
                            if val >= 400:
                                per_person = val
                                break

                # 備用：取最後一格純數字
                if per_person == 0:
                    for cell in reversed(cells):
                        clean = re.sub(r'[,$\s]', '', cell)
                        if re.match(r'^\d+$', clean):
                            val = int(clean)
                            if val >= 400:
                                per_person = val
                                break

                if per_person > 0 and level not in FIXED_AMOUNTS:
                    amounts[level] = per_person
                    print(f'[INFO] {level}等獎金: ${per_person:,}')

    except Exception as e:
        print(f'[WARN] Playwright/lottolyzer 失敗: {e}，使用預設值')

    # 確保固定獎金正確
    for lv, amt in FIXED_AMOUNTS.items():
        amounts[lv] = amt  # 固定獎金強制覆蓋

    print('[INFO] 最終各等獎金:')
    for lv in sorted(amounts.keys()):
        print(f'  {lv}等: ${amounts[lv]:,}')

    return amounts

# ── 中獎判斷 ──────────────────────────────────────────────
PRIZE_TABLE = {
    (6,False):(1,'頭獎'), (6,True):(1,'頭獎'),
    (5,True): (2,'貳獎'), (5,False):(3,'參獎'),
    (4,True): (4,'肆獎'), (4,False):(5,'伍獎'),
    (3,True): (6,'陸獎'), (2,True): (7,'柒獎'),
    (3,False):(8,'普獎'),
}

def check_prize(u_nums, u_sp, w_nums, w_sp):
    if not u_nums or not w_nums: return 0,'未中獎'
    matched = len(set(u_nums) & set(w_nums))
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

    # 1. 抓開獎號碼
    result = fetch_latest()
    print(f'[INFO] 號碼結果: {result}')
    if not result.get('numbers') or not result.get('period'):
        print('[ERROR] 無法取得開獎號碼，終止'); return

    period    = result['period']
    draw_date = result.get('date', now_tw().strftime('%Y/%m/%d'))
    win_nums  = result['numbers']
    win_sp    = result['special']
    print(f'[INFO] 期別：{period} | 日期：{draw_date}')
    print(f'[INFO] 開獎：{win_nums} 特別號：{win_sp}')

    # 2. 抓各等獎金（Playwright + lottolyzer）
    prize_amounts = fetch_prize_amounts_lottolyzer(period)

    # 3. 寫入 Firestore
    db.collection('draws_results').document(f'tw_{period}').set({
        'lotType':'tw', 'lotName':'台灣大樂透',
        'period':period, 'drawDate':draw_date,
        'numbers':win_nums, 'special':win_sp,
        'prizeAmounts': {str(k):v for k,v in prize_amounts.items()},
        'updatedAt': firestore.SERVER_TIMESTAMP,
    })
    print(f'[INFO] 已寫入 Firestore: tw_{period}')

    # 4. 核對
    start_dt, end_dt = get_valid_window(draw_date)
    print(f'[INFO] 有效時間：{start_dt} ~ {end_dt}')

    docs = (db.collection('draws')
              .where(filter=firestore.FieldFilter('lotType','==','tw'))
              .where(filter=firestore.FieldFilter('prizeLevel','==',0))
              .stream())

    checked = won = 0
    for doc in docs:
        data = doc.to_dict()
        ca   = data.get('createdAt')
        if not ca or not hasattr(ca,'seconds'): continue
        ct   = datetime.fromtimestamp(ca.seconds, tz=TZ_TW)
        if not (start_dt <= ct <= end_dt): continue

        u_sp = data.get('special',[])
        if isinstance(u_sp,list): u_sp = u_sp[0] if u_sp else None

        lv,desc = check_prize(data.get('numbers',[]), u_sp, win_nums, win_sp)
        upd = {
            'prizeLevel':lv, 'prizeDesc':desc,
            'checkedAt': firestore.SERVER_TIMESTAMP,
            'drawPeriod':period, 'winNumbers':win_nums, 'winSpecial':win_sp,
        }
        if lv > 0:
            upd['prizeAmount'] = prize_amounts.get(lv, 0)
            won += 1
            print(f'[WIN] {data.get("catName")} 中獎 {lv}等 {desc}！'
                  f' 獎金：${upd["prizeAmount"]:,}')
        doc.reference.update(upd)
        checked += 1

    print(f'[INFO] 核對：{checked} 筆，中獎 {won} 筆')
    print('[INFO] 完畢 ✓')

if __name__ == '__main__':
    main()
