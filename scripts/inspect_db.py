"""
資料庫唯讀檢查：只統計數量與格式，不修改任何資料，不輸出貓名、email、uid 等個資。
結果寫成 Markdown，由 workflow 貼到 PR 留言。
"""
import os, json, statistics
from collections import Counter
from datetime import datetime, timezone, timedelta
import firebase_admin
from firebase_admin import credentials, firestore, auth

TZ = timezone(timedelta(hours=8))

def init():
    cred = credentials.Certificate(json.loads(os.environ['FIREBASE_SERVICE_ACCOUNT']))
    firebase_admin.initialize_app(cred)
    return firestore.client()

def ts(v):
    if v is None: return None
    if hasattr(v, 'timestamp'): return datetime.fromtimestamp(v.timestamp(), TZ)
    return None

def size_stats(sizes):
    if not sizes: return '無'
    s = sorted(sizes)
    return f'最小 {s[0]/1024:.0f}KB／中位數 {statistics.median(s)/1024:.0f}KB／最大 {s[-1]/1024:.0f}KB'

def keyset_report(docs):
    c = Counter()
    for d in docs: c.update(d.keys())
    n = len(docs)
    return ', '.join(f'`{k}`({v}/{n})' for k, v in sorted(c.items()))

def main():
    db = init()
    out = ['## 資料庫唯讀檢查結果', f'執行時間：{datetime.now(TZ):%Y/%m/%d %H:%M}（台灣時間）', '']

    # ── 帳號（只計數）───────────────────────────
    try:
        providers, n_users = Counter(), 0
        page = auth.list_users()
        while page:
            for u in page.users:
                n_users += 1
                providers.update(p.provider_id for p in u.provider_data)
            page = page.get_next_page()
        out += ['### 帳號', f'- 註冊人數：{n_users}', f'- 登入方式：{dict(providers)}', '']
    except Exception as e:
        out += ['### 帳號', f'- 無法讀取：{type(e).__name__}', '']

    # ── draws ──────────────────────────────────
    draws = [d.to_dict() for d in db.collection('draws').stream()]
    out += ['### draws（選號紀錄）', f'- 總筆數：{len(draws)}']
    out.append(f'- 樂透類型：{dict(Counter(d.get("lotType") for d in draws))}')
    out.append(f'- 主號碼數量分布：{dict(Counter((d.get("lotType"), len(d.get("numbers") or [])) for d in draws))}')
    out.append(f'- 特別號數量分布：{dict(Counter((d.get("lotType"), len(d.get("special") or [])) for d in draws))}')
    out.append(f'- 不同使用者數：{len(set(d.get("uid") for d in draws if d.get("uid")))}，無 uid 的筆數：{sum(1 for d in draws if not d.get("uid"))}')
    out.append(f'- 有 catId：{sum(1 for d in draws if d.get("catId"))}，無 catId：{sum(1 for d in draws if not d.get("catId"))}')
    out.append(f'- 已對獎（有 checkedAt）：{sum(1 for d in draws if d.get("checkedAt"))}')
    out.append(f'- 中獎等級分布：{dict(Counter(d.get("prizeLevel", 0) for d in draws))}')
    out.append(f'- 總獎金：{sum(d.get("prizeAmount") or 0 for d in draws):,}')
    out.append(f'- 有 drawPeriod：{sum(1 for d in draws if d.get("drawPeriod"))}')
    created = [ts(d.get('createdAt')) for d in draws]
    created_ok = sorted(c for c in created if c)
    out.append(f'- createdAt 缺少或格式不對：{sum(1 for c in created if not c)}')
    if created_ok:
        out.append(f'- 選號時間範圍：{created_ok[0]:%Y/%m/%d} ～ {created_ok[-1]:%Y/%m/%d}')
        by_month = Counter(c.strftime('%Y-%m') for c in created_ok)
        out.append(f'- 每月筆數：{dict(sorted(by_month.items()))}')
    photo_sizes = [len(d['photoThumb']) for d in draws if isinstance(d.get('photoThumb'), str)]
    out.append(f'- 有照片：{len(photo_sizes)} 筆，大小：{size_stats(photo_sizes)}')
    bad_photo = sum(1 for d in draws if isinstance(d.get('photoThumb'), str) and not d['photoThumb'].startswith('data:image/'))
    out.append(f'- 照片不是 data:image 格式：{bad_photo}')
    out.append(f'- 欄位出現次數：{keyset_report(draws)}')
    out.append('')

    # ── cats ───────────────────────────────────
    cats = [d.to_dict() for d in db.collection('cats').stream()]
    out += ['### cats（貓咪主檔）', f'- 總數：{len(cats)}']
    out.append(f'- 不同使用者數：{len(set(c.get("uid") for c in cats if c.get("uid")))}')
    out.append(f'- 每位使用者貓數分布：{dict(Counter(Counter(c.get("uid") for c in cats).values()))}')
    pairs = Counter((c.get('uid'), c.get('catName')) for c in cats)
    out.append(f'- 同一使用者重複同名的貓：{sum(1 for v in pairs.values() if v > 1)} 組')
    cat_photo = [len(c['photoThumb']) for c in cats if isinstance(c.get('photoThumb'), str)]
    out.append(f'- 照片大小：{size_stats(cat_photo)}')
    sum_cat_draws = sum(c.get('totalDraws') or 0 for c in cats)
    linked = sum(1 for d in draws if d.get('catId'))
    out.append(f'- cats.totalDraws 加總：{sum_cat_draws}（對照：draws 有 catId 的筆數 {linked}）')
    out.append(f'- 欄位出現次數：{keyset_report(cats)}')
    out.append('')

    # ── stats ──────────────────────────────────
    g = db.collection('stats').document('global').get()
    out += ['### stats/global', f'- 內容：{g.to_dict() if g.exists else "不存在"}（實際 draws 筆數 {len(draws)}）', '']

    # ── draws_results ──────────────────────────
    res = sorted((d.to_dict() for d in db.collection('draws_results').stream()), key=lambda r: str(r.get('period')))
    out += ['### draws_results（開獎結果）', f'- 筆數：{len(res)}', '',
            '| 期別 | 開獎日 | 號碼 | 特別號 | 獎金欄位 |', '|---|---|---|---|---|']
    for r in res:
        pa = r.get('prizeAmounts') or {}
        out.append(f'| {r.get("period")} | {r.get("drawDate")} | {r.get("numbers")} | {r.get("special")} | '
                   + ', '.join(f'{k}:{v}' for k, v in sorted(pa.items(), key=lambda x: int(x[0]))) + ' |')
    out.append('')

    # ── 其他集合 ────────────────────────────────
    others = [c.id for c in db.collections() if c.id not in ('draws', 'cats', 'stats', 'draws_results')]
    out += ['### 其他集合', f'- {others or "無"}']

    text = '\n'.join(out)
    print(text)
    with open('inspect_result.md', 'w', encoding='utf-8') as f:
        f.write(text)

if __name__ == '__main__':
    main()
