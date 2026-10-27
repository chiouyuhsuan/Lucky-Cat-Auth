"""
第 7 段：舊資料整理（一次性）

做的事：
  1. 備份：把 draws、cats、stats、draws_results 全部複製到 backups/{時間}/items/（安全規則不允許任何人從前端讀取）
  2. 舊選號（沒有 schema 欄位的台灣大樂透）用官方資料重新對獎，補齊開獎日、對中幾碼等欄位
     - 不刪除舊紀錄裡貓自選的特別號（畫面上顯示為灰色劃線、不計入）
     - 「我買了」不補（舊紀錄無從得知）
  3. 沒有 catId 的選號，依「同一使用者＋同一貓名」補上（剛好對到一隻才補）
  4. 開獎結果：用官方資料重抓 2026-04 起所有期數並覆蓋；刪除不是官方來源、也不在官方清單中的文件
  5. 刪除已停用的 stats/global

用法：
  python scripts/migrate_legacy.py                 試跑（預設，不寫入），列出所有會做的變更
  python scripts/migrate_legacy.py --apply         正式執行（先備份再寫入）
  python scripts/migrate_legacy.py --restore ID    依備份還原（ID 為備份時間，例如 20261027-1300）
"""
import os, sys, json, argparse
from collections import defaultdict
from datetime import datetime, date
from firebase_admin import firestore

sys.path.insert(0, os.path.dirname(__file__))
from lottery_rules import TZ_TW, PRIZE_NAMES, prize_level, prize_amount, assign_draw
from lottery_job import init_db, to_tw, fetch_official

SINCE = date(2026, 4, 1)          # 最早一筆選號在 2026-04-22
COLLECTIONS = ['draws', 'cats', 'stats', 'draws_results']


def short(i):
    return f'`{i[:6]}`'


def backup(db, out):
    bid = datetime.now(TZ_TW).strftime('%Y%m%d-%H%M%S')
    root = db.collection('backups').document(bid)
    root.set({'createdAt': firestore.SERVER_TIMESTAMP, 'collections': COLLECTIONS, 'note': '第 7 段舊資料整理前備份'})
    n, batch = 0, db.batch()
    for col in COLLECTIONS:
        for d in db.collection(col).stream():
            batch.set(root.collection('items').document(f'{col}__{d.id}'), {'col': col, 'id': d.id, 'data': d.to_dict()})
            n += 1
            if n % 200 == 0:
                batch.commit(); batch = db.batch()
    batch.commit()
    # 讀回確認筆數
    back = sum(1 for _ in root.collection('items').stream())
    if back != n:
        sys.exit(f'備份筆數不符：寫入 {n}，讀回 {back}，中止')
    out.append(f'- ✅ 已備份 {n} 筆到 `backups/{bid}`（讀回確認相符）')
    return bid


def restore(db, bid):
    root = db.collection('backups').document(bid)
    if not root.get().exists:
        sys.exit(f'找不到備份 {bid}')
    items = list(root.collection('items').stream())
    batch, n = db.batch(), 0
    for it in items:
        x = it.to_dict()
        batch.set(db.collection(x['col']).document(x['id']), x['data'])
        n += 1
        if n % 200 == 0:
            batch.commit(); batch = db.batch()
    batch.commit()
    print(f'已依備份 {bid} 還原 {n} 筆（備份之後新增的文件不受影響）')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--restore', default='')
    ap.add_argument('--summary', default='migrate_summary.md')
    args = ap.parse_args()
    db = init_db()
    if args.restore:
        restore(db, args.restore); return
    apply = args.apply
    out = [f'## 第 7 段：舊資料整理{"" if apply else "（試跑，未寫入）"}',
           f'執行時間：{datetime.now(TZ_TW):%Y/%m/%d %H:%M}（台灣時間）', '']

    draws = [(d.id, d.reference, d.to_dict()) for d in db.collection('draws').stream()]
    cats = [(c.id, c.to_dict()) for c in db.collection('cats').stream()]
    results = {d.id: d.to_dict() for d in db.collection('draws_results').stream()}
    stats_doc = db.collection('stats').document('global').get()
    official, problems = fetch_official(SINCE)
    if not official:
        sys.exit('抓不到官方開獎資料，中止')
    by_period = {o['period']: o for o in official}
    out.append(f'- 官方開獎資料：{SINCE:%Y-%m} 起共 {len(official)} 期'
               + (f'（{len(problems)} 筆異常已略過）' if problems else ''))

    if apply:
        out.append('')
        bid = backup(db, out)
        out.append(f'- 若需還原：在 Actions 執行本工作並填入還原 ID `{bid}`')

    # ── 1. 舊選號重新對獎、補欄位 ─────────────────────────
    by_name = defaultdict(list)
    for cid, c in cats:
        by_name[(c.get('uid'), c.get('catName'))].append(cid)

    out += ['', '### 1. 舊選號補齊（用官方資料重新對獎）', '',
            '| 紀錄 | 貓 | 選號時間 | 期別（舊→新） | 結果（舊→新） | 補 catId |', '|---|---|---|---|---|---|']
    legacy = [(i, r, d) for i, r, d in draws if d.get('schema') is None and d.get('lotType') == 'tw']
    changed_result, updates = 0, []
    for i, ref, d in sorted(legacy, key=lambda x: to_tw(x[2].get('createdAt')) or datetime.min.replace(tzinfo=TZ_TW)):
        ct = to_tw(d.get('createdAt'))
        o = assign_draw(ct, official) if ct else None
        if not o or not o['prizesFinal']:
            out.append(f'| {short(i)} | {d.get("catName")} | — | 無法對應期別，略過 | | |'); continue
        lv, matched, has_sp = prize_level(d.get('numbers') or [], o['numbers'], o['special'])
        amt = prize_amount(lv, o['prizes'])
        upd = {
            'tracked': True, 'legacy': True,
            'drawPeriod': o['period'], 'drawDate': o['date'].isoformat(),
            'winNumbers': o['numbers'], 'winSpecial': o['special'],
            'matchCount': matched, 'matchSpecial': has_sp,
            'prizeLevel': lv, 'prizeDesc': PRIZE_NAMES.get(lv, '未中獎'), 'prizeAmount': amt,
            'lotName': '台灣大樂透', 'lotFlag': '🇹🇼',
        }
        if not d.get('checkedAt'):
            upd['checkedAt'] = firestore.SERVER_TIMESTAMP
        cat_fill = ''
        if not d.get('catId'):
            ids = by_name.get((d.get('uid'), d.get('catName'))) or []
            if len(ids) == 1:
                upd['catId'] = ids[0]; cat_fill = '✓'
            else:
                cat_fill = f'對到 {len(ids)} 隻，不補'
        old_p, old_lv = str(d.get('drawPeriod') or '—'), int(d.get('prizeLevel') or 0)
        diff = old_p != o['period'] or old_lv != lv or int(d.get('prizeAmount') or 0) != amt
        changed_result += diff
        mark = ' ⚠️' if diff else ''
        out.append(f'| {short(i)}{mark} | {d.get("catName")} | {ct:%m/%d %H:%M} | {old_p} → {o["period"]} | '
                   f'{PRIZE_NAMES.get(old_lv, "未中獎")} {d.get("prizeAmount") or 0} → {PRIZE_NAMES.get(lv, "未中獎")} {amt}'
                   f'（{matched} 碼{"＋特" if has_sp else ""}） | {cat_fill} |')
        updates.append((ref, upd))
    out.append(f'\n- 共 {len(legacy)} 筆舊選號，{len(updates)} 筆會補齊；**期別或結果有變動：{changed_result} 筆**（⚠️ 標示）')

    # 新格式選號若缺 catId（理論上沒有），也一併檢查
    missing_new = [i for i, _, d in draws if d.get('schema') == 2 and not d.get('catId')]
    if missing_new:
        out.append(f'- ⚠️ 新格式選號缺 catId：{[short(i) for i in missing_new]}（不處理，請回報）')

    # ── 2. 開獎結果重抓 ───────────────────────────────────
    out += ['', '### 2. 開獎結果（官方資料覆蓋）']
    fixed_dates = []
    for o in official:
        old = results.get(f'tw_{o["period"]}')
        new_date = o['date'].strftime('%Y/%m/%d')
        if old and old.get('drawDate') != new_date:
            fixed_dates.append(f'{o["period"]}：{old.get("drawDate")} → {new_date}')
    official_ids = {f'tw_{o["period"]}' for o in official}
    to_delete = [k for k, v in results.items() if k not in official_ids and v.get('source') != 'official']
    out.append(f'- 會寫入 {len(official)} 期官方資料；其中 **{len(fixed_dates)} 期日期更正**')
    for x in fixed_dates:
        out.append(f'  - {x}')
    out.append(f'- 會刪除不在官方清單中的舊文件：{to_delete or "無"}')

    # ── 3. 停用的統計文件 ─────────────────────────────────
    out += ['', '### 3. 已停用的 stats/global',
            f'- {"會刪除：" + json.dumps(stats_doc.to_dict(), ensure_ascii=False) if stats_doc.exists else "不存在，略過"}']

    # ── 寫入 ──────────────────────────────────────────────
    if apply:
        batch, n = db.batch(), 0
        def add(op):
            nonlocal batch, n
            op(batch); n += 1
            if n % 400 == 0:
                batch.commit(); batch = db.batch()
        for ref, upd in updates:
            add(lambda b, ref=ref, upd=upd: b.update(ref, upd))
        for o in official:
            doc = db.collection('draws_results').document(f'tw_{o["period"]}')
            add(lambda b, doc=doc, o=o: b.set(doc, {
                'lotType': 'tw', 'lotName': '台灣大樂透', 'source': 'official',
                'period': o['period'], 'drawDate': o['date'].strftime('%Y/%m/%d'),
                'numbers': o['numbers'], 'special': o['special'],
                'prizes': {str(k): v for k, v in o['prizes'].items()},
                'prizeAmounts': {str(k): prize_amount(k, o['prizes']) for k in range(1, 9)},
                'prizesFinal': o['prizesFinal'], 'updatedAt': firestore.SERVER_TIMESTAMP}))
        for k in to_delete:
            add(lambda b, k=k: b.delete(db.collection('draws_results').document(k)))
        if stats_doc.exists:
            add(lambda b: b.delete(stats_doc.reference))
        batch.commit()
        out += ['', f'### ✅ 已寫入（{n} 項操作）', '- 貓咪統計會在接下來的對獎工作中重新計算']

    text = '\n'.join(out)
    print(text)
    with open(args.summary, 'w', encoding='utf-8') as f:
        f.write(text)


if __name__ == '__main__':
    main()
