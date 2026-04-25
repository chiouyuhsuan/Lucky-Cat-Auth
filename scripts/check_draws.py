"""
台灣大樂透對獎核對腳本
執行時機：每週二、週五 23:00（台灣時間，fetch_lottery 跑完後 1 小時）
功能：
  1. 從 draws_results 讀取最新期開獎號碼與獎金
  2. 找出有效時間窗口內的用戶選號
  3. 核對號碼，更新中獎狀態與獎金
"""

import os, json, re
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

# ── 讀取最新開獎結果 ──────────────────────────────────────
def get_latest_draw_result(db):
    """
    從 draws_results 找今天或昨天的最新一期
    """
    today = now_tw()
    # 嘗試今天和昨天的日期（避免時區邊界問題）
    for delta in [0, 1]:
        check_date = today - timedelta(days=delta)
        date_str = check_date.strftime('%Y/%m/%d')
        # 查詢當天的開獎結果
        docs = list(db.collection('draws_results')
                      .where(filter=firestore.FieldFilter('drawDate', '==', date_str))
                      .where(filter=firestore.FieldFilter('lotType', '==', 'tw'))
                      .stream())
        if docs:
            data = docs[0].to_dict()
            print(f'[INFO] 找到開獎結果: 第{data.get("period")}期 {date_str}')
            return data

    print('[WARN] 今日和昨日都找不到開獎結果，嘗試讀最新一筆...')
    # fallback: 讀最新一筆
    docs = list(db.collection('draws_results')
                  .where(filter=firestore.FieldFilter('lotType', '==', 'tw'))
                  .order_by('updatedAt', direction=firestore.Query.DESCENDING)
                  .limit(1)
                  .stream())
    if docs:
        data = docs[0].to_dict()
        print(f'[INFO] 使用最新期: 第{data.get("period")}期 {data.get("drawDate")}')
        return data
    return None

# ── 有效時間窗口 ──────────────────────────────────────────
def get_valid_window(draw_date_str):
    draw = datetime.strptime(draw_date_str, '%Y/%m/%d').replace(tzinfo=TZ_TW)
    end  = draw.replace(hour=20, minute=0, second=0)
    back = 4 if draw.weekday() == 1 else 3  # 週二往前4天，週五往前3天
    start = (draw - timedelta(days=back)).replace(hour=20, minute=31, second=0)
    return start, end

# ── 中獎判斷 ──────────────────────────────────────────────
PRIZE_TABLE = {
    (6,False):(1,'頭獎'), (6,True):(1,'頭獎'),
    (5,True): (2,'貳獎'), (5,False):(3,'參獎'),
    (4,True): (4,'肆獎'), (4,False):(5,'伍獎'),
    (3,True): (6,'陸獎'), (2,True): (7,'柒獎'),
    (3,False):(8,'普獎'),
}

def check_prize(u_nums, u_sp, w_nums, w_sp):
    if not u_nums or not w_nums: return 0, '未中獎'
    matched = len(set(u_nums) & set(w_nums))
    has_sp  = (int(u_sp) == int(w_sp)) if u_sp else False
    lv, desc = PRIZE_TABLE.get((matched, has_sp), (0, '未中獎'))
    return lv, desc

def main():
    print(f'[INFO] check_draws 開始 {now_tw().strftime("%Y/%m/%d %H:%M:%S")} 台灣時間')
    db = init_firebase()
    print('[INFO] Firebase 連線成功')

    # 1. 讀取最新開獎結果
    draw_result = get_latest_draw_result(db)
    if not draw_result:
        print('[ERROR] 找不到開獎結果，請先執行 fetch_lottery.py'); return

    period    = draw_result['period']
    draw_date = draw_result['drawDate']
    win_nums  = draw_result['numbers']
    win_sp    = draw_result['special']
    prize_amounts = {int(k): v for k, v in draw_result.get('prizeAmounts', {}).items()}

    print(f'[INFO] 核對期別：{period} | 日期：{draw_date}')
    print(f'[INFO] 開獎號碼：{win_nums} 特別號：{win_sp}')
    print(f'[INFO] 各等獎金：{prize_amounts}')

    # 2. 有效時間窗口
    start_dt, end_dt = get_valid_window(draw_date)
    print(f'[INFO] 有效選號時間：{start_dt} ~ {end_dt}')

    # 3. 查詢所有待核對的大樂透選號（單條件查詢，不需要複合索引）
    all_docs = list(db.collection('draws')
                      .where(filter=firestore.FieldFilter('lotType', '==', 'tw'))
                      .stream())
    print(f'[INFO] 查到 {len(all_docs)} 筆 lotType=tw 的紀錄')

    checked = won = skipped = 0
    for doc in all_docs:
        data = doc.to_dict()

        # 只核對還沒有結果的（prizeLevel == 0 且 checkedAt 不存在）
        if data.get('checkedAt') is not None:
            continue
        if data.get('prizeLevel', 0) != 0:
            continue

        # 檢查時間窗口
        ca = data.get('createdAt')
        ct = None
        if ca is None:
            # createdAt 不存在，改用 date 欄位推算（格式 2026.04.23）
            date_str = data.get('date', '')
            if date_str:
                try:
                    d = datetime.strptime(date_str.replace('.', '/'), '%Y/%m/%d').replace(tzinfo=TZ_TW)
                    ct = d.replace(hour=12, minute=0)
                    print(f'[INFO] {data.get("catName")} 用date推算: {ct.strftime("%m/%d %H:%M")}')
                except Exception as e:
                    print(f'[SKIP] {data.get("catName")} date解析失敗: {e}')
        elif hasattr(ca, 'seconds'):
            ct = datetime.fromtimestamp(ca.seconds, tz=TZ_TW)
        elif hasattr(ca, 'timestamp'):
            ct = datetime.fromtimestamp(ca.timestamp(), tz=TZ_TW)
        elif isinstance(ca, (int, float)):
            ct = datetime.fromtimestamp(ca, tz=TZ_TW)
        else:
            print(f'[SKIP] {data.get("catName")} createdAt格式未知: {type(ca)}')
        if ct is None:
            skipped += 1
            continue
        in_window = start_dt <= ct <= end_dt
        print(f'[CHECK] {data.get("catName")} createdAt={ct.strftime("%m/%d %H:%M")} 在窗口={in_window}')
        if not in_window:
            skipped += 1
            continue

        # 核對號碼
        u_sp = data.get('special', [])
        if isinstance(u_sp, list):
            u_sp = u_sp[0] if u_sp else None

        lv, desc = check_prize(data.get('numbers', []), u_sp, win_nums, win_sp)
        upd = {
            'prizeLevel': lv,
            'prizeDesc': desc,
            'checkedAt': firestore.SERVER_TIMESTAMP,
            'drawPeriod': period,
            'winNumbers': win_nums,
            'winSpecial': win_sp,
        }
        if lv > 0:
            upd['prizeAmount'] = prize_amounts.get(lv, 0)
            won += 1
            print(f'[WIN] 🎉 {data.get("catName")} 中獎 {lv}等 {desc}！獎金：${upd["prizeAmount"]:,}')
        else:
            upd['prizeAmount'] = 0

        doc.reference.update(upd)
        checked += 1

    print(f'[INFO] 核對完成：{checked} 筆，中獎 {won} 筆，跳過 {skipped} 筆')
    print('[INFO] check_draws 完畢 ✓')

if __name__ == '__main__':
    main()
