"""
對獎規則單元測試
執行：python -m unittest discover -s tests -p "test_*.py"
"""
import sys, os, unittest
from datetime import datetime, date
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from lottery_rules import (prize_level, prize_amount, assign_draw, parse_official,
                           TZ_TW, JACKPOT_GUARANTEE)

# 第 115000098 期（2026-10-20）官方資料
WIN = [2, 5, 19, 33, 40, 43]
SP = 6
OFFICIAL_98 = {
    "period": 115000098, "lotteryDate": "2026-10-20T00:00:00",
    "drawNumberSize": [2, 5, 19, 33, 40, 43, 6],
    "jackpotAssign": {"prize": 31066556, "lastPrize": 31253010, "winnerCount": 0, "perPrize": 0},
    "secondAssign": {"prize": 2462592, "lastPrize": 2477372, "winnerCount": 3, "perPrize": 1646654},
    "thirdAssign": {"prize": 2652023, "lastPrize": 0, "winnerCount": 29, "perPrize": 91449},
    "fourthAssign": {"prize": 1704871, "lastPrize": 0, "winnerCount": 98, "perPrize": 17396},
    "fifthAssign": {"prize": 4306000, "lastPrize": 0, "winnerCount": 2153, "perPrize": 2000},
    "sixthAssign": {"prize": 2895000, "lastPrize": 0, "winnerCount": 2895, "perPrize": 1000},
    "seventhAssign": {"prize": 12710400, "lastPrize": 0, "winnerCount": 31776, "perPrize": 400},
    "normalAssign": {"prize": 15941200, "lastPrize": 0, "winnerCount": 39853, "perPrize": 400},
}


class PrizeLevel(unittest.TestCase):
    def check(self, mine, expect):
        self.assertEqual(prize_level(mine, WIN, SP)[0], expect, mine)

    def test_all_tiers(self):
        self.check([2, 5, 19, 33, 40, 43], 1)   # 6 碼
        self.check([2, 5, 19, 33, 40, 6], 2)    # 5 碼 + 特別號
        self.check([2, 5, 19, 33, 40, 1], 3)    # 5 碼
        self.check([2, 5, 19, 33, 6, 1], 4)     # 4 碼 + 特別號
        self.check([2, 5, 19, 33, 7, 1], 5)     # 4 碼
        self.check([2, 5, 19, 6, 7, 1], 6)      # 3 碼 + 特別號
        self.check([2, 5, 6, 7, 8, 1], 7)       # 2 碼 + 特別號 = 柒獎
        self.check([2, 5, 19, 7, 8, 1], 8)      # 3 碼 = 普獎
        self.check([2, 5, 7, 8, 9, 1], 0)       # 2 碼
        self.check([2, 6, 7, 8, 9, 1], 0)       # 1 碼 + 特別號
        self.check([6, 7, 8, 9, 10, 1], 0)      # 只中特別號

    def test_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            prize_level([1, 2, 3, 4, 5], WIN, SP)
        with self.assertRaises(ValueError):
            prize_level([1, 1, 3, 4, 5, 6], WIN, SP)

    def test_old_bug_would_differ(self):
        # 舊程式用「貓自己選的特別號」比對；新規則看開出的特別號是否在玩家 6 碼內
        lv, matched, has_sp = prize_level([2, 5, 6, 7, 8, 1], WIN, SP)
        self.assertEqual((lv, matched, has_sp), (7, 2, True))


class Official(unittest.TestCase):
    def setUp(self):
        self.r = parse_official(OFFICIAL_98)

    def test_parse(self):
        self.assertEqual(self.r['period'], '115000098')
        self.assertEqual(self.r['date'], date(2026, 10, 20))
        self.assertEqual(self.r['numbers'], WIN)
        self.assertEqual(self.r['special'], SP)
        self.assertTrue(self.r['prizesFinal'])

    def test_amounts(self):
        p = self.r['prizes']
        self.assertEqual(prize_amount(2, p), 1646654)          # 有人中：官方每注金額
        self.assertEqual(prize_amount(8, p), 400)
        self.assertEqual(prize_amount(0, p), 0)
        # 頭獎無人中：估算獨得金額，至少 1 億
        self.assertEqual(prize_amount(1, p), JACKPOT_GUARANTEE)

    def test_not_final_when_fixed_tiers_empty(self):
        raw = dict(OFFICIAL_98, fifthAssign={"prize": 0, "lastPrize": 0, "winnerCount": 0, "perPrize": 0})
        self.assertFalse(parse_official(raw)['prizesFinal'])

    def test_bad_numbers(self):
        with self.assertRaises(ValueError):
            parse_official(dict(OFFICIAL_98, drawNumberSize=[1, 2, 3, 4, 5, 6]))
        with self.assertRaises(ValueError):
            parse_official(dict(OFFICIAL_98, drawNumberSize=[1, 2, 3, 4, 5, 6, 6]))


class Assign(unittest.TestCase):
    # 2026 春節：2/24–2/28 連續開獎，之後回到週二、週五
    DRAWS = [{'period': p, 'date': d} for p, d in [
        ('115000024', date(2026, 2, 20)), ('115000025', date(2026, 2, 24)),
        ('115000026', date(2026, 2, 25)), ('115000027', date(2026, 2, 26)),
        ('115000028', date(2026, 2, 27)), ('115000029', date(2026, 2, 28)),
        ('115000030', date(2026, 3, 3)),
    ]]

    def at(self, s):
        return datetime.strptime(s, '%Y-%m-%d %H:%M').replace(tzinfo=TZ_TW)

    def test_normal(self):
        self.assertEqual(assign_draw(self.at('2026-02-20 19:59'), self.DRAWS)['period'], '115000024')
        self.assertEqual(assign_draw(self.at('2026-02-20 20:00'), self.DRAWS)['period'], '115000025')

    def test_lunar_new_year_daily_draws(self):
        # 週三晚上選號：前端以為是週五，實際上週四就開獎
        self.assertEqual(assign_draw(self.at('2026-02-25 21:00'), self.DRAWS)['period'], '115000027')
        self.assertEqual(assign_draw(self.at('2026-02-28 08:00'), self.DRAWS)['period'], '115000029')
        self.assertEqual(assign_draw(self.at('2026-02-28 20:30'), self.DRAWS)['period'], '115000030')

    def test_not_drawn_yet(self):
        self.assertIsNone(assign_draw(self.at('2026-03-03 20:00'), self.DRAWS))

    def test_timezone_independent(self):
        # 同一時刻用 UTC 表示，結果相同
        utc = self.at('2026-02-20 19:59').astimezone(tz=None)
        self.assertEqual(assign_draw(utc, self.DRAWS)['period'], '115000024')


if __name__ == '__main__':
    unittest.main()
