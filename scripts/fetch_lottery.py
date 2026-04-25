"""
台灣大樂透開獎號碼 + 獎金抓取腳本
執行時機：每週二、週五 22:00（台灣時間）
功能：
  1. 抓最新開獎號碼（atsunny.tw / taiwanlottery 套件）
  2. 抓各等獎金（Playwright + lottolyzer）
  3. 寫入 Firestore draws_results 集合
"""

import os, json, re, requests
from bs4 import BeautifulSoup
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, timezone

TZ_TW = timezone(timedelta(hours=8))
def now_tw():
    return datetime.now(TZ_TW)

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

def fetch_latest_numbers():
    for name, fn in [('taiwanlottery套件', fetch_via_package),
                     ('atsunny.tw', fetch_via_atsunny)]:
        print(f'[INFO] 嘗試: {name}')
        r = fn()
        if r and r.get('numbers') and r.get('period'):
            print(f'[INFO] {name} 成功')
            return r
    return {}

# ── 各等獎金：Playwright + lottolyzer ────────────────────
FIXED_AMOUNTS = {5: 2000, 6: 1000, 7: 400, 8: 400}

def fetch_prize_amounts(period):
    amounts = dict(FIXED_AMOUNTS)
    amounts.update({1: 100000000, 2: 2000000, 3: 80000, 4: 16000})
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
            try:
                page.wait_for_selector('table', timeout=15000)
                print('[INFO] 找到表格')
            except:
                print('[WARN] 等待表格逾時')
            html = page.content()
            browser.close()

        soup = BeautifulSoup(html, 'lxml')
        print(f'[DEBUG] 頁面大小: {len(html)} bytes')

        prize_map = {
            '頭獎':1,'壹獎':1,'一獎':1,
            '二獎':2,'貳獎':2,
            '三獎':3,'參獎':3,
            '四獎':4,'肆獎':4,
            '五獎':5,'伍獎':5,
            '六獎':6,'陸獎':6,
            '七獎':7,'柒獎':7,
            '八獎':8,'捌獎':8,'普獎':8,
        }

        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = [td.get_text(strip=True) for td in row.find_all(['td','th'])]
                if len(cells) < 2: continue
                level = None
                for cell in cells[:2]:
                    for name, lv in prize_map.items():
                        if name in cell:
                            level = lv; break
                    if level: break
                if level is None: continue

                per_person = 0
                for cell in cells:
                    if '每人各分' in cell or '每人' in cell:
                        m = re.search(r'\$?([\d,]+)$', cell.strip())
                        if m:
                            val = int(m.group(1).replace(',',''))
                            if val >= 400:
                                per_person = val; break
                if per_person == 0:
                    for cell in reversed(cells):
                        clean = re.sub(r'[,$\s]', '', cell)
                        if re.match(r'^\d+$', clean):
                            val = int(clean)
                            if val >= 400:
                                per_person = val; break

                if per_person > 0 and level not in FIXED_AMOUNTS:
                    amounts[level] = per_person
                    print(f'[INFO] {level}等獎金: ${per_person:,}')

    except Exception as e:
        print(f'[WARN] Playwright/lottolyzer 失敗: {e}，使用預設值')

    for lv, amt in FIXED_AMOUNTS.items():
        amounts[lv] = amt

    print('[INFO] 最終各等獎金:')
    for lv in sorted(amounts.keys()):
        print(f'  {lv}等: ${amounts[lv]:,}')
    return amounts

def main():
    print(f'[INFO] fetch_lottery 開始 {now_tw().strftime("%Y/%m/%d %H:%M:%S")} 台灣時間')
    db = init_firebase()
    print('[INFO] Firebase 連線成功')

    result = fetch_latest_numbers()
    print(f'[INFO] 號碼結果: {result}')
    if not result.get('numbers') or not result.get('period'):
        print('[ERROR] 無法取得開獎號碼，終止'); return

    period    = result['period']
    draw_date = result.get('date', now_tw().strftime('%Y/%m/%d'))
    win_nums  = result['numbers']
    win_sp    = result['special']
    print(f'[INFO] 期別：{period} | 日期：{draw_date}')
    print(f'[INFO] 開獎：{win_nums} 特別號：{win_sp}')

    prize_amounts = fetch_prize_amounts(period)

    db.collection('draws_results').document(f'tw_{period}').set({
        'lotType': 'tw', 'lotName': '台灣大樂透',
        'period': period, 'drawDate': draw_date,
        'numbers': win_nums, 'special': win_sp,
        'prizeAmounts': {str(k): v for k, v in prize_amounts.items()},
        'updatedAt': firestore.SERVER_TIMESTAMP,
    })
    print(f'[INFO] 已寫入 Firestore: tw_{period}')
    print('[INFO] fetch_lottery 完畢 ✓')

if __name__ == '__main__':
    main()
