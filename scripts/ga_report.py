"""
GA4 報表：用 GA4 Data API 抓網站數據，輸出成 Markdown（給 Claude 讀、也貼在 Actions 摘要）

用法：
  GA4_PROPERTY_ID=123456789 FIREBASE_SERVICE_ACCOUNT='{...}' python scripts/ga_report.py [--days 7] [--out ga_report.md]

權限：服務帳戶要在 GA4「管理 → 資源存取權管理」加成「檢視者」，
     並在 Google Cloud 專案啟用 Google Analytics Data API。
"""
import os, sys, json, argparse
from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from google.analytics.data_v1beta.types import (
    RunReportRequest, DateRange, Dimension, Metric, OrderBy, FilterExpression, Filter)

FUNNEL = ['page_view', 'in_app_browser', 'login_prompt_show', 'photo_select', 'photo_upload',
          'generate_numbers', 'card_view', 'share', 'video_made', 'save_draw', 'login', 'sign_up',
          'mark_purchased', 'new_round', 'select_lottery', 'region_default_lottery', 'language_change',
          'js_error', 'save_draw_error', 'card_error']


def client():
    info = json.loads(os.environ['FIREBASE_SERVICE_ACCOUNT'])
    cred = service_account.Credentials.from_service_account_info(
        info, scopes=['https://www.googleapis.com/auth/analytics.readonly'])
    return BetaAnalyticsDataClient(credentials=cred)


def run(c, prop, dims, mets, start, end='today', order=None, limit=50, flt=None):
    req = RunReportRequest(
        property=f'properties/{prop}',
        dimensions=[Dimension(name=d) for d in dims],
        metrics=[Metric(name=m) for m in mets],
        date_ranges=[DateRange(start_date=start, end_date=end)],
        limit=limit)
    if order:
        req.order_bys = [order]
    if flt:
        req.dimension_filter = flt
    r = c.run_report(req)
    return [([v.value for v in row.dimension_values], [v.value for v in row.metric_values]) for row in r.rows]


def table(head, rows):
    out = ['| ' + ' | '.join(head) + ' |', '|' + '---|' * len(head)]
    out += ['| ' + ' | '.join(str(x) for x in r) + ' |' for r in rows]
    return out


def num(v):
    try:
        f = float(v)
        return f'{f:,.0f}' if f.is_integer() or f > 100 else f'{f:.2f}'
    except ValueError:
        return v


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--out', default='ga_report.md')
    a = ap.parse_args()
    prop = os.environ.get('GA4_PROPERTY_ID', '').strip()
    if not prop.isdigit():
        sys.exit('GA4_PROPERTY_ID 未設定（要填數字的資源 ID，不是 G- 開頭的評估 ID）')
    c = client()
    d = a.days
    cur, prev = f'{d}daysAgo', f'{d * 2}daysAgo'
    out = [f'# LuckyCat GA4 報表（最近 {d} 天）', '']

    # 1. 總覽：本期 vs 上一期
    mets = ['activeUsers', 'newUsers', 'sessions', 'screenPageViews', 'engagementRate', 'averageSessionDuration']
    now = run(c, prop, [], mets, cur, 'yesterday')
    before = run(c, prop, [], mets, prev, f'{d + 1}daysAgo')
    names = ['活躍使用者', '新使用者', '工作階段', '瀏覽次數', '互動率', '平均工作階段秒數']
    rows = []
    for i, n in enumerate(names):
        x = now[0][1][i] if now else '0'
        y = before[0][1][i] if before else '0'
        rows.append([n, num(x), num(y)])
    out += ['## 總覽（不含今天）'] + table(['指標', f'最近 {d} 天', f'前 {d} 天'], rows) + ['']

    # 2. 每日活躍使用者
    daily = run(c, prop, ['date'], ['activeUsers', 'sessions', 'eventCount'], f'{max(d, 14)}daysAgo',
                order=OrderBy(dimension=OrderBy.DimensionOrderBy(dimension_name='date')))
    out += ['## 每日'] + table(['日期', '活躍使用者', '工作階段', '事件數'],
                              [[r[0][0], num(r[1][0]), num(r[1][1]), num(r[1][2])] for r in daily]) + ['']

    # 3. 選號漏斗：各事件次數與人數
    ev = {r[0][0]: r[1] for r in run(c, prop, ['eventName'], ['eventCount', 'totalUsers'], cur, limit=200)}
    out += ['## 事件（選號漏斗）'] + table(['事件', '次數', '人數'],
                                    [[e, num(ev[e][0]) if e in ev else 0, num(ev[e][1]) if e in ev else 0] for e in FUNNEL]) + ['']
    others = sorted([(k, v) for k, v in ev.items() if k not in FUNNEL], key=lambda kv: -float(kv[1][0]))
    if others:
        out += ['### 其他事件'] + table(['事件', '次數', '人數'], [[k, num(v[0]), num(v[1])] for k, v in others]) + ['']

    # 4. 流量來源
    src = run(c, prop, ['sessionSource', 'sessionMedium'], ['sessions', 'activeUsers', 'engagementRate'], cur,
              order=OrderBy(metric=OrderBy.MetricOrderBy(metric_name='sessions'), desc=True), limit=15)
    out += ['## 流量來源'] + table(['來源', '媒介', '工作階段', '使用者', '互動率'],
                               [[r[0][0], r[0][1], num(r[1][0]), num(r[1][1]), num(r[1][2])] for r in src]) + ['']

    # 5. 裝置、瀏覽器（看 App 內建瀏覽器比例）、國家
    for title, dim in [('裝置', 'deviceCategory'), ('瀏覽器', 'browser'), ('作業系統', 'operatingSystem'), ('國家', 'country')]:
        rs = run(c, prop, [dim], ['activeUsers', 'sessions'], cur,
                 order=OrderBy(metric=OrderBy.MetricOrderBy(metric_name='activeUsers'), desc=True), limit=10)
        out += [f'## {title}'] + table([title, '使用者', '工作階段'], [[r[0][0], num(r[1][0]), num(r[1][1])] for r in rs]) + ['']

    # 6. 頁面
    pg = run(c, prop, ['pagePath'], ['screenPageViews', 'activeUsers', 'userEngagementDuration'], cur,
             order=OrderBy(metric=OrderBy.MetricOrderBy(metric_name='screenPageViews'), desc=True), limit=15)
    out += ['## 頁面'] + table(['網址', '瀏覽', '使用者', '互動秒數'],
                             [[r[0][0], num(r[1][0]), num(r[1][1]), num(r[1][2])] for r in pg]) + ['']

    # 7. 網域（新舊網址各有多少人）
    host = run(c, prop, ['hostName'], ['activeUsers', 'sessions'], cur)
    out += ['## 網域'] + table(['網域', '使用者', '工作階段'], [[r[0][0], num(r[1][0]), num(r[1][1])] for r in host]) + ['']

    text = '\n'.join(out)
    print(text)
    with open(a.out, 'w', encoding='utf-8') as f:
        f.write(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as f:
            f.write(text + '\n')


if __name__ == '__main__':
    main()
