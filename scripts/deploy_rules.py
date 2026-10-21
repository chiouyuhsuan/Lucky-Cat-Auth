"""
發布 firestore.rules 到正式環境（用 GitHub secret 裡的 service account）
流程：建立新的 ruleset → 把 cloud.firestore 的發布指向它 → 讀回確認
舊版本保留在 Firebase Console 的規則歷史，可隨時還原。
"""
import os, json, sys, requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request

info = json.loads(os.environ['FIREBASE_SERVICE_ACCOUNT'])
cred = service_account.Credentials.from_service_account_info(
    info, scopes=['https://www.googleapis.com/auth/cloud-platform'])
cred.refresh(Request())
H = {'Authorization': 'Bearer ' + cred.token}
pid = info['project_id']
BASE = f'https://firebaserules.googleapis.com/v1/projects/{pid}'
src = open('firestore.rules', encoding='utf-8').read()

before = requests.get(f'{BASE}/releases/cloud.firestore', headers=H)
before.raise_for_status()
print('發布前版本：', before.json()['rulesetName'])

r = requests.post(f'{BASE}/rulesets', headers=H,
                  json={'source': {'files': [{'name': 'firestore.rules', 'content': src}]}})
if not r.ok:
    sys.exit(f'建立規則失敗（語法錯誤？）：{r.status_code} {r.text}')
name = r.json()['name']
print('新規則：', name)

u = requests.patch(f'{BASE}/releases/cloud.firestore', headers=H,
                   json={'release': {'name': f'projects/{pid}/releases/cloud.firestore', 'rulesetName': name}})
if not u.ok:
    sys.exit(f'發布失敗：{u.status_code} {u.text}')

after = requests.get(f'{BASE}/releases/cloud.firestore', headers=H).json()
if after['rulesetName'] != name:
    sys.exit(f'發布後讀回的版本不符：{after["rulesetName"]}')
live = requests.get(f'https://firebaserules.googleapis.com/v1/{name}', headers=H).json()
if live['source']['files'][0]['content'] != src:
    sys.exit('發布後讀回的內容不符')
print('✓ 已發布並確認，更新時間', after.get('updateTime'))
with open(os.environ.get('GITHUB_STEP_SUMMARY', '/dev/null'), 'a') as f:
    f.write(f'### Firestore 規則已發布\n- 前：`{before.json()["rulesetName"].split("/")[-1]}`\n'
            f'- 後：`{name.split("/")[-1]}`\n- 時間：{after.get("updateTime")}\n')
