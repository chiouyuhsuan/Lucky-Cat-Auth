"""
台灣大樂透對獎規則（純函式，不連網、不碰資料庫，方便測試）
規則依據：docs/LOTTERY_RULES.md
"""
from datetime import datetime, date, timedelta, timezone

TZ_TW = timezone(timedelta(hours=8))
CUTOFF_HOUR = 20  # 開獎日 20:00 停止銷售（與 js/lottery.js 相同）

PRIZE_NAMES = {1: '頭獎', 2: '貳獎', 3: '參獎', 4: '肆獎',
               5: '伍獎', 6: '陸獎', 7: '柒獎', 8: '普獎'}

# 官方 API 各等獎欄位
ASSIGN_KEYS = {1: 'jackpotAssign', 2: 'secondAssign', 3: 'thirdAssign', 4: 'fourthAssign',
               5: 'fifthAssign', 6: 'sixthAssign', 7: 'seventhAssign', 8: 'normalAssign'}

JACKPOT_GUARANTEE = 100_000_000  # 頭獎保證 1 億（獨得時）


def prize_level(numbers, win_numbers, win_special):
    """
    numbers: 玩家 6 個號碼；win_numbers: 開獎 6 個號碼；win_special: 開獎特別號
    回傳 (等級 0-8, 對中主號數, 是否含特別號)
    """
    mine = set(int(n) for n in numbers)
    if len(mine) != 6:
        raise ValueError(f'玩家號碼必須是 6 個不重複的號碼：{numbers}')
    matched = len(mine & set(int(n) for n in win_numbers))
    has_sp = int(win_special) in mine
    if matched == 6:
        lv = 1
    elif matched == 5:
        lv = 2 if has_sp else 3
    elif matched == 4:
        lv = 4 if has_sp else 5
    elif matched == 3:
        lv = 6 if has_sp else 8
    elif matched == 2 and has_sp:
        lv = 7
    else:
        lv = 0
    return lv, matched, has_sp


def prize_amount(level, prizes):
    """
    依官方公布的該期各等獎金計算單注獎金。
    prizes: {等級(int): {'perPrize', 'winnerCount', 'pool'}}
    該等級官方無人中獎時（perPrize 為 0），以「如果貓咪獨得」估算：該等獎金池；頭獎至少保證 1 億。
    """
    if level == 0:
        return 0
    p = prizes.get(level) or {}
    if p.get('winnerCount', 0) > 0 and p.get('perPrize', 0) > 0:
        return int(p['perPrize'])
    pool = int(p.get('pool', 0))
    if level == 1:
        return max(pool, JACKPOT_GUARANTEE)
    return pool


def draw_deadline(draw_date):
    """該期的銷售截止時間（台灣時間開獎日 20:00）"""
    return datetime(draw_date.year, draw_date.month, draw_date.day, CUTOFF_HOUR, tzinfo=TZ_TW)


def assign_draw(created_at, draws):
    """
    找出這組號碼屬於哪一期：銷售截止時間（開獎日 20:00）晚於選號時間的第一期。
    用官方實際開獎日判斷，所以春節連續開獎等特殊排程也會正確。
    created_at: 選號時間（含時區）
    draws: 依日期排序的官方開獎清單，每筆含 'date'(date)
    回傳該期 dict；還沒開獎則回傳 None
    """
    for d in draws:
        if draw_deadline(d['date']) > created_at:
            return d
    return None


def parse_official(item):
    """
    把官方 API 一筆 lotto649Res 轉成內部格式；資料異常時丟出 ValueError
    """
    period = str(item['period'])
    d = datetime.strptime(item['lotteryDate'][:10], '%Y-%m-%d').date()
    nums = [int(n) for n in item['drawNumberSize']]
    if len(nums) != 7 or len(set(nums)) != 7 or not all(1 <= n <= 49 for n in nums):
        raise ValueError(f'第 {period} 期號碼異常：{nums}')
    prizes = {}
    for lv, key in ASSIGN_KEYS.items():
        a = item.get(key) or {}
        prizes[lv] = {
            'perPrize': int(a.get('perPrize') or 0),
            'winnerCount': int(a.get('winnerCount') or 0),
            'pool': int(a.get('prize') or 0) + int(a.get('lastPrize') or 0),
        }
    # 伍獎以下是固定獎且每期必定有人中；若還是 0，代表官方尚未公布獎金
    final = all(prizes[lv]['winnerCount'] > 0 for lv in (5, 6, 7, 8))
    return {
        'period': period,
        'date': d,
        'numbers': sorted(nums[:6]),
        'special': nums[6],
        'prizes': prizes,
        'prizesFinal': final,
    }
