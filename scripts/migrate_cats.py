"""
一次性遷移腳本：把舊有 draws 裡的貓咪補建到 cats 集合
只需要跑一次
"""
import os, json
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timezone

def init_firebase():
    sa_json = os.environ.get('FIREBASE_SERVICE_ACCOUNT')
    if not sa_json:
        raise RuntimeError('FIREBASE_SERVICE_ACCOUNT 未設定')
    cred = credentials.Certificate(json.loads(sa_json))
    firebase_admin.initialize_app(cred)
    return firestore.client()

def main():
    db = init_firebase()
    print('[INFO] Firebase 連線成功')

    # 讀取所有 draws（已登入的，有 uid）
    docs = list(db.collection('draws').stream())
    print(f'[INFO] 共 {len(docs)} 筆 draws')

    # 按 uid + catName 分組，找最新一筆
    cat_map = {}  # key: uid_catName -> best draw data
    for doc in docs:
        data = doc.to_dict()
        uid = data.get('uid')
        cat_name = data.get('catName', '')
        if not uid or not cat_name:
            continue
        key = uid + '___' + cat_name
        if key not in cat_map:
            cat_map[key] = data
        else:
            # 保留最新一筆
            existing_ca = cat_map[key].get('createdAt')
            new_ca = data.get('createdAt')
            if new_ca and existing_ca:
                if hasattr(new_ca, 'seconds') and hasattr(existing_ca, 'seconds'):
                    if new_ca.seconds > existing_ca.seconds:
                        cat_map[key] = data

    print(f'[INFO] 找到 {len(cat_map)} 隻獨特貓咪（uid+名字組合）')

    # 為每隻貓建立 cats 文件（如果不存在）
    created = skipped = 0
    for key, data in cat_map.items():
        uid = data.get('uid')
        cat_name = data.get('catName', '')

        # 查是否已存在
        existing = list(db.collection('cats')
                         .where(filter=firestore.FieldFilter('uid', '==', uid))
                         .where(filter=firestore.FieldFilter('catName', '==', cat_name))
                         .stream())
        if existing:
            print(f'[SKIP] {cat_name} 已存在 cats 集合')
            skipped += 1
            continue

        # 計算這隻貓的統計
        total_draws = sum(1 for d in docs
                         if d.to_dict().get('uid') == uid
                         and d.to_dict().get('catName') == cat_name)
        total_wins = sum(1 for d in docs
                        if d.to_dict().get('uid') == uid
                        and d.to_dict().get('catName') == cat_name
                        and (d.to_dict().get('prizeLevel') or 0) > 0)
        total_prize = sum((d.to_dict().get('prizeAmount') or 0) for d in docs
                         if d.to_dict().get('uid') == uid
                         and d.to_dict().get('catName') == cat_name)

        # 建立 cats 文件
        db.collection('cats').add({
            'uid': uid,
            'catName': cat_name,
            'photoThumb': data.get('photoThumb'),
            'country': data.get('country', '未知'),
            'countryCode': data.get('countryCode', ''),
            'city': data.get('city', '未知'),
            'totalDraws': total_draws,
            'totalWins': total_wins,
            'totalPrize': total_prize,
            'createdAt': firestore.SERVER_TIMESTAMP,
            'lastDrawAt': firestore.SERVER_TIMESTAMP,
        })
        print(f'[CREATE] {cat_name} (uid:{uid[:8]}...) '
              f'totalDraws={total_draws} totalWins={total_wins} totalPrize={total_prize}')
        created += 1

    print(f'[INFO] 完成！建立 {created} 筆，跳過 {skipped} 筆')

if __name__ == '__main__':
    main()
