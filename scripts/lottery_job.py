"""
台灣大樂透：抓官方開獎 → 對獎 → 重算貓咪統計（取代舊的 fetch_lottery / check_draws / check_lottery）

用法：
  python scripts/lottery_job.py                 正式執行（會寫入資料庫）
  python scripts/lottery_job.py --dry-run       只讀不寫，列出會做的變更
  python scripts/lottery_job.py --dry-run --include-legacy
  python scripts/lottery_job.py --fix-legacy ID1,ID2
                                                只把指定的舊紀錄用新規則對獎並寫入（尚未對過獎的才會處理），
                                                寫入前把原始內容記錄在摘要裡
                                                另外預覽舊紀錄（第 7 段）用新規則重算的結果

資料來源：台灣彩券官方 API（開獎號碼、日期、各等獎每注金額）
重複執行是安全的：已對過獎的紀錄不會重算，開獎結果用期別當文件 ID 覆寫。
"""
import os, sys, json, time, argparse
from collections import defaultdict
from datetime import datetime, date
import requests
import firebase_admin
from firebase_admin import credentials, firestore

sys.path.insert(0, os.path.dirname(__file__))
from lottery_rules import (TZ_TW, PRIZE_NAMES, prize_level, prize_amount,
                           assign_draw, parse_official,
                           USD_TWD, PB_PRIZE_NAMES, PB_PRIZE_USD, pb_prize_level,
                           parse_ny_powerball, pb_assign)

API = 'https://api.taiwanlottery.com/TLCAPIWeB/Lottery/Lotto649Result'
# 美國 Powerball：紐約州政府公開資料（官方開獎號碼，每期開獎後更新）
PB_API = 'https://data.ny.gov/resource/d6yy-54nr.json'
MAX_MONTHS = 24


def log(*a):
    print(*a, flush=True)


def init_db():
    sa = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if not sa:
        raise RuntimeError('FIREBASE_SERVICE_ACCOUNT 未設定')
    firebase_admin.initialize_app(credentials.Certificate(json.loads(sa)))
    return firestore.client()


def to_tw(ts):
    """Firestore 時間戳 → 台灣時間 datetime；無效則回傳 None"""
    if ts is None or not hasattr(ts, 'timestamp'):
        return None
    return datetime.fromtimestamp(ts.timestamp(), TZ_TW)


# ── 官方開獎資料 ────────────────────────────────────────
def fetch_month(y, m):
    url = f'{API}?period&month={y}-{m:02d}&pageNum=1&pageSize=50'
    last = None
    for attempt in range(4):
        try:
            r = requests.get(url, timeout=30, headers={'User-Agent': 'Mozilla/5.0 LuckyCat'})
            r.raise_for_status()
            body = r.json()
            if body.get('rtCode') != 0:
                raise RuntimeError(f'rtCode={body.get("rtCode")} {body.get("rtMsg")}')
            return (body.get('content') or {}).get('lotto649Res') or []
        except Exception as e:
            last = e
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f'抓取 {y}-{m:02d} 失敗：{last}')


def months_between(start, end):
    y, m = start.year, start.month
    out = []
    while (y, m) <= (end.year, end.month) and len(out) < MAX_MONTHS:
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def fetch_official(since):
    today = datetime.now(TZ_TW).date()
    draws, problems = {}, []
    for y, m in months_between(since, today):
        for item in fetch_month(y, m):
            try:
                d = parse_official(item)
                draws[d['period']] = d
            except Exception as e:
                problems.append(str(e))
    return sorted(draws.values(), key=lambda d: d['date']), problems


# ── 主流程 ──────────────────────────────────────────────
def fetch_powerball(limit=60):
    """最近 limit 期 Powerball 開獎，依日期由舊到新；回傳 (清單, 問題)"""
    last = None
    for attempt in range(4):
        try:
            r = requests.get(PB_API, params={'$order': 'draw_date DESC', '$limit': limit}, timeout=30,
                             headers={'User-Agent': 'Mozilla/5.0 LuckyCat'})
            r.raise_for_status()
            rows, problems = [], []
            for row in r.json():
                try:
                    rows.append(parse_ny_powerball(row))
                except (ValueError, KeyError) as e:
                    problems.append(f'Powerball {row.get("draw_date")}：{e}')
            rows.sort(key=lambda d: d['date'])
            return rows, problems
        except Exception as e:
            last = e
            time.sleep(3 * (attempt + 1))
    return [], [f'Powerball 開獎資料抓取失敗：{last}']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--include-legacy', action='store_true')
    ap.add_argument('--fix-legacy', default='')
    ap.add_argument('--summary', default='lottery_summary.md')
    args = ap.parse_args()
    dry = args.dry_run
    now = datetime.now(TZ_TW)
    db = init_db()

    out = [f'## 對獎排程{"（試跑，未寫入）" if dry else ""}',
           f'執行時間：{now:%Y/%m/%d %H:%M}（台灣時間）', '']

    # 1. 讀取所有選號
    all_draws = [(doc.id, doc.reference, doc.to_dict()) for doc in db.collection('draws').stream()]

    def is_pending_new(d):
        return (d.get('schema') == 2 and d.get('lotType') == 'tw' and d.get('tracked')
                and not d.get('checkedAt'))

    def is_legacy_tw(d):
        return d.get('schema') is None and d.get('lotType') == 'tw'

    pending = [(i, r, d) for i, r, d in all_draws if is_pending_new(d)]
    pending_us = [(i, r, d) for i, r, d in all_draws
                  if d.get('schema') == 2 and d.get('lotType') == 'us' and d.get('tracked')
                  and not d.get('checkedAt') and d.get('targetDrawDate')]
    legacy = [(i, r, d) for i, r, d in all_draws if is_legacy_tw(d)] if args.include_legacy else []

    # 2. 抓官方開獎：涵蓋最早一筆待對獎紀錄到今天（至少抓上個月起）
    fix_ids = [x.strip() for x in args.fix_legacy.split(',') if x.strip()]
    # 可給完整 ID 或至少 6 碼的開頭，但必須剛好對到一筆
    fix, fix_msgs = [], []
    for x in fix_ids:
        hits = [(i, r, d) for i, r, d in all_draws if i == x or (len(x) >= 6 and i.startswith(x))]
        if len(hits) == 1:
            fix.append(hits[0])
        else:
            fix_msgs.append(f'- `{x}`：對到 {len(hits)} 筆，略過（需剛好一筆）')
    created = [to_tw(d.get('createdAt')) for _, _, d in pending + legacy + fix]
    created = [c for c in created if c]
    floor = date(now.year if now.month > 1 else now.year - 1, now.month - 1 if now.month > 1 else 12, 1)
    since = min([c.date() for c in created] + [floor])
    official, problems = fetch_official(since)
    by_period = {d['period']: d for d in official}
    out.append(f'### 官方開獎資料')
    out.append(f'- 抓取 {since:%Y-%m} 起共 {len(official)} 期'
               + (f'，最新：第 {official[-1]["period"]} 期 {official[-1]["date"]}' if official else ''))
    not_final = [d['period'] for d in official if not d['prizesFinal']]
    if not_final:
        out.append(f'- 獎金尚未公布：{not_final}（下次執行再對）')
    for p in problems:
        out.append(f'- ⚠️ 資料異常已略過：{p}')

    # 3. 寫入開獎結果（期別當文件 ID，重複執行會覆寫成同樣內容）
    if not dry:
        batch, n = db.batch(), 0
        for d in official:
            batch.set(db.collection('draws_results').document(f'tw_{d["period"]}'), {
                'lotType': 'tw', 'lotName': '台灣大樂透', 'source': 'official',
                'period': d['period'], 'drawDate': d['date'].strftime('%Y/%m/%d'),
                'numbers': d['numbers'], 'special': d['special'],
                'prizes': {str(k): v for k, v in d['prizes'].items()},
                'prizeAmounts': {str(k): prize_amount(k, d['prizes']) for k in range(1, 9)},
                'prizesFinal': d['prizesFinal'],
                'updatedAt': firestore.SERVER_TIMESTAMP,
            })
            n += 1
            if n % 400 == 0:
                batch.commit(); batch = db.batch()
        batch.commit()

    # 4. 對獎
    def check(items, write):
        rows, stats = [], defaultdict(int)
        for draw_id, ref, d in items:
            ct = to_tw(d.get('createdAt'))
            if not ct:
                stats['無選號時間'] += 1
                continue
            r = assign_draw(ct, official)
            if not r:
                stats['尚未開獎'] += 1
                continue
            if not r['prizesFinal']:
                stats['等待獎金公布'] += 1
                continue
            try:
                lv, matched, has_sp = prize_level(d.get('numbers') or [], r['numbers'], r['special'])
            except ValueError as e:
                stats['號碼格式錯誤'] += 1
                log('[SKIP]', draw_id, e)
                continue
            amt = prize_amount(lv, r['prizes'])
            stats['已對獎'] += 1
            if lv:
                stats['中獎'] += 1
            rows.append((draw_id, d, r, lv, matched, has_sp, amt))
            if write:
                ref.update({
                    'drawPeriod': r['period'],
                    'drawDate': r['date'].isoformat(),
                    'winNumbers': r['numbers'], 'winSpecial': r['special'],
                    'matchCount': matched, 'matchSpecial': has_sp,
                    'prizeLevel': lv, 'prizeDesc': PRIZE_NAMES.get(lv, '未中獎'),
                    'prizeAmount': amt,
                    'checkedAt': firestore.SERVER_TIMESTAMP,
                })
                d.update({'prizeLevel': lv, 'prizeAmount': amt, 'checkedAt': True})
        return rows, stats

    rows, stats = check(pending, write=not dry)
    out += ['', '### 新選號對獎', f'- 待對獎 {len(pending)} 筆：{dict(stats) or "無"}']
    for draw_id, d, r, lv, matched, has_sp, amt in rows:
        moved = '' if d.get('targetDrawDate') == r['date'].isoformat() else f'（選號時預估 {d.get("targetDrawDate")}）'
        out.append(f'- `{draw_id[:6]}` 第 {r["period"]} 期 {r["date"]}{moved}：對中 {matched} 碼'
                   f'{"＋特別號" if has_sp else ""} → {PRIZE_NAMES.get(lv, "未中獎")}'
                   + (f' ${amt:,}' if amt else ''))

    # 4p. 美國 Powerball：抓開獎 → 存開獎結果 → 對獎（獎金換算台幣存 prizeAmount，美元另存 prizeAmountUsd）
    pb_draws, pb_problems = fetch_powerball()
    out += ['', '### Powerball',
            f'- 抓取 {len(pb_draws)} 期' + (f'，最新：{pb_draws[-1]["date"]} {pb_draws[-1]["numbers"]} + {pb_draws[-1]["special"]}' if pb_draws else '')]
    out += [f'- ⚠️ {p}' for p in pb_problems]
    if not dry and pb_draws:
        batch = db.batch()
        for d in pb_draws[-30:]:
            batch.set(db.collection('draws_results').document(f'us_{d["date"]:%Y%m%d}'), {
                'lotType': 'us', 'lotName': 'US Powerball', 'source': 'data.ny.gov',
                'period': d['date'].strftime('%Y%m%d'), 'drawDate': d['date'].strftime('%Y/%m/%d'),
                'numbers': d['numbers'], 'special': d['special'],
                'prizesUsd': {str(k): v for k, v in PB_PRIZE_USD.items()}, 'usdTwd': USD_TWD,
                'updatedAt': firestore.SERVER_TIMESTAMP,
            })
        batch.commit()
    pb_stats = defaultdict(int)
    for draw_id, ref, d in pending_us:
        r = pb_assign(d['targetDrawDate'], pb_draws)
        if not r:
            pb_stats['尚未開獎'] += 1
            continue
        try:
            lv, matched, pb = pb_prize_level(d.get('numbers') or [], d.get('special') or [], r['numbers'], r['special'])
        except ValueError as e:
            pb_stats['號碼格式錯誤'] += 1
            log('[SKIP]', draw_id, e)
            continue
        usd = PB_PRIZE_USD.get(lv, 0)
        pb_stats['已對獎'] += 1
        if lv:
            pb_stats['中獎'] += 1
        out.append(f'- `{draw_id[:6]}` {r["date"]}：白球對中 {matched} 碼{"＋Powerball" if pb else ""} → '
                   f'{PB_PRIZE_NAMES.get(lv, "未中獎")}' + (f' US${usd:,}（NT${usd * USD_TWD:,}）' if usd else '')
                   + ('（⚠️ 頭獎，金額要人工確認）' if lv == 1 else ''))
        if not dry:
            ref.update({
                'drawPeriod': r['date'].strftime('%Y%m%d'),
                'drawDate': r['date'].isoformat(),
                'winNumbers': r['numbers'], 'winSpecial': r['special'],
                'matchCount': matched, 'matchSpecial': pb,
                'prizeLevel': lv, 'prizeDesc': PB_PRIZE_NAMES.get(lv, '未中獎'),
                'prizeAmount': usd * USD_TWD, 'prizeAmountUsd': usd,
                'checkedAt': firestore.SERVER_TIMESTAMP,
            })
            d.update({'prizeLevel': lv, 'prizeAmount': usd * USD_TWD, 'checkedAt': True})
    out.append(f'- 待對獎 {len(pending_us)} 筆：{dict(pb_stats) or "無"}')

    # 4a. 指定修正的舊紀錄（只處理舊格式、尚未對過獎的大樂透）
    if fix_ids:
        out += ['', '### 指定修正的舊紀錄']
        out += fix_msgs
        ok = []
        for i, r, d in fix:
            if not is_legacy_tw(d):
                out.append(f'- `{i}`：不是舊格式的大樂透紀錄，略過'); continue
            if d.get('checkedAt'):
                out.append(f'- `{i}`：已經對過獎，略過（整批重算在第 7 段處理）'); continue
            before = {k: (str(v) if hasattr(v, 'timestamp') else v)
                      for k, v in sorted(d.items()) if k != 'photoThumb'}
            if before.get('uid'):   # repo 公開，使用者編號只留末 4 碼
                before['uid'] = '…' + str(before['uid'])[-4:]
            out += [f'- `{i}` 修改前完整內容（照片除外）：', '```json',
                    json.dumps(before, ensure_ascii=False, default=str, indent=1), '```']
            ok.append((i, r, d))
        frows, fstats = check(ok, write=not dry)
        for draw_id, d, r, lv, matched, has_sp, amt in frows:
            out.append(f'- `{draw_id}` {"（試跑）" if dry else "已寫入"}：第 {r["period"]} 期 {r["date"]}，'
                       f'開獎 {r["numbers"]} 特別號 {r["special"]}，貓的號碼 {d.get("numbers")} '
                       f'→ 對中 {matched} 碼{"＋特別號" if has_sp else ""}，{PRIZE_NAMES.get(lv, "未中獎")}'
                       + (f' ${amt:,}' if amt else ''))
        if fstats and not frows:
            out.append(f'- 未寫入：{dict(fstats)}')

    # 4b. 舊紀錄重算預覽（只在 --include-legacy 時，且永遠不寫入）
    if args.include_legacy:
        lrows, lstats = check(legacy, write=False)
        out += ['', '### 舊紀錄用新規則重算（預覽，未寫入）', f'- 共 {len(legacy)} 筆：{dict(lstats)}', '',
                '| 紀錄 | 選號時間 | 舊：期別 → 結果 | 新：期別 → 結果 |', '|---|---|---|---|']
        for draw_id, d, r, lv, matched, has_sp, amt in lrows:
            old = f'{d.get("drawPeriod", "—")} → {PRIZE_NAMES.get(d.get("prizeLevel", 0), "未中獎")}' \
                  + (f' ${d.get("prizeAmount", 0):,}' if d.get('prizeAmount') else '')
            new = f'{r["period"]} → {PRIZE_NAMES.get(lv, "未中獎")}' + (f' ${amt:,}' if amt else '') \
                  + f'（{matched} 碼{"＋特" if has_sp else ""}）'
            mark = '' if (str(d.get('drawPeriod')) == r['period'] and d.get('prizeLevel', 0) == lv) else ' ⚠️'
            out.append(f'| `{draw_id[:6]}`{mark} | {to_tw(d["createdAt"]):%m/%d %H:%M} | {old} | {new} |')

    # 5. 重算每隻貓的統計（只算台灣大樂透，舊紀錄沿用其現有結果直到第 7 段重算）
    cats = [(c.id, c.reference, c.to_dict()) for c in db.collection('cats').stream()]
    # 舊選號有些沒有 catId，用「同一使用者＋同一貓名」對應（與個人頁的做法相同）；對應到多隻就放棄
    by_name = defaultdict(list)
    for cid, _, c in cats:
        by_name[(c.get('uid'), c.get('catName'))].append(cid)

    def cat_of(d):
        if d.get('catId'):
            return d['catId']
        ids = by_name.get((d.get('uid'), d.get('catName'))) or []
        return ids[0] if len(ids) == 1 else None

    per_cat = defaultdict(lambda: {'twDraws': 0, 'checked': 0, 'wins': 0, 'prize': 0, 'bestLevel': 0})
    # Powerball 另外統計（中獎率分開排）；獎金是台幣，排行榜的累積獎金會把兩種加起來
    per_cat_us = defaultdict(lambda: {'draws': 0, 'checked': 0, 'wins': 0, 'prize': 0, 'bestLevel': 0})
    unlinked = 0
    for _, _, d in all_draws:
        if d.get('lotType') == 'us' and d.get('tracked') and d.get('schema') == 2:
            cid = cat_of(d)
            if cid:
                u = per_cat_us[cid]
                u['draws'] += 1
                if d.get('checkedAt'):
                    u['checked'] += 1
                    lv = int(d.get('prizeLevel') or 0)
                    if lv > 0:
                        u['wins'] += 1
                        u['prize'] += int(d.get('prizeAmount') or 0)
                        u['bestLevel'] = lv if not u['bestLevel'] else min(u['bestLevel'], lv)
            continue
        if d.get('lotType') != 'tw' or d.get('tracked') is False:
            continue
        cid = cat_of(d)
        if not cid:
            unlinked += 1
            continue
        s = per_cat[cid]
        s['twDraws'] += 1
        if d.get('checkedAt'):
            s['checked'] += 1
            lv = int(d.get('prizeLevel') or 0)
            if lv > 0:
                s['wins'] += 1
                s['prize'] += int(d.get('prizeAmount') or 0)
                s['bestLevel'] = lv if not s['bestLevel'] else min(s['bestLevel'], lv)

    changed = []
    for cid, ref, c in cats:
        s = per_cat.get(cid, {'twDraws': 0, 'checked': 0, 'wins': 0, 'prize': 0, 'bestLevel': 0})
        s = dict(s, winRate=round(s['wins'] / s['checked'], 4) if s['checked'] else 0)
        if cid in per_cat_us:
            u = per_cat_us[cid]
            s['us'] = dict(u, winRate=round(u['wins'] / u['checked'], 4) if u['checked'] else 0)
        total_wins = s['wins'] + s.get('us', {}).get('wins', 0)
        total_prize = s['prize'] + s.get('us', {}).get('prize', 0)
        if c.get('stats') == s and c.get('totalWins') == total_wins and c.get('totalPrize') == total_prize:
            continue
        changed.append((cid, c, s))
        if not dry:
            ref.update({'stats': s, 'totalWins': total_wins, 'totalPrize': total_prize,
                        'lastCheckedAt': firestore.SERVER_TIMESTAMP})
    out += ['', '### 貓咪統計', f'- 需要更新 {len(changed)} 隻'
            + (f'；{unlinked} 筆大樂透選號對應不到貓（第 7 段處理）' if unlinked else '')]
    for cid, c, s in changed:
        out.append(f'- `{cid[:6]}`：中獎 {c.get("totalWins", 0)}→{s["wins"]}、獎金 {c.get("totalPrize", 0)}→{s["prize"]}、'
                   f'大樂透 {s["twDraws"]} 筆（已對 {s["checked"]}）')

    text = '\n'.join(out)
    log(text)
    with open(args.summary, 'w', encoding='utf-8') as f:
        f.write(text)
    if problems and not official:
        sys.exit('官方開獎資料完全抓不到')


if __name__ == '__main__':
    main()
