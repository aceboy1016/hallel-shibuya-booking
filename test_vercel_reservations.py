#!/usr/bin/env python3
"""
Vercel本番環境での予約システムテスト
"""

import requests
import json
from datetime import datetime, timedelta

# Vercel本番環境URL
BASE_URL = "https://hallelshibuyabooking-bjjls7h66-aceboys-projects.vercel.app"

def login_and_get_session():
    """ログインしてセッションを取得"""
    session = requests.Session()

    # ログインページにアクセス
    login_page = session.get(f"{BASE_URL}/login")
    print(f"ログインページアクセス: {login_page.status_code}")

    # ログイン実行
    login_data = {"password": "hallel"}
    login_response = session.post(f"{BASE_URL}/login", data=login_data, allow_redirects=False)
    print(f"ログイン実行: {login_response.status_code}")

    if login_response.status_code in [302, 303]:
        print("✅ ログイン成功")
        return session
    else:
        print("❌ ログイン失敗")
        return None

def test_add_manual_reservation(session):
    """手動予約追加テスト"""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    reservation_data = {
        "date": tomorrow,
        "start": "14:00",
        "end": "15:00",
        "customer_name": "テスト 太郎"
    }

    response = session.post(f"{BASE_URL}/api/reservations", json=reservation_data)
    print(f"予約追加テスト: {response.status_code}")
    print(f"レスポンス: {response.text}")

    return response.status_code == 200

def test_gmail_sync(session):
    """Gmail同期テスト"""
    response = session.post(f"{BASE_URL}/api/gmail/sync")
    print(f"Gmail同期テスト: {response.status_code}")
    print(f"レスポンス: {response.text}")

    return response.status_code == 200

def check_reservations():
    """現在の予約状況確認"""
    response = requests.get(f"{BASE_URL}/api/reservations")
    print(f"予約確認: {response.status_code}")

    if response.status_code == 200:
        data = response.json()
        total = sum(len(reservations) for reservations in data.values())
        print(f"📊 総予約数: {total}件")

        for date, reservations in data.items():
            if reservations:
                print(f"{date}: {len(reservations)}件")
                for res in reservations:
                    customer = res.get('customer_name', 'N/A')
                    time_slot = f"{res['start']}-{res['end']}"
                    print(f"  - {time_slot} {customer}")
    else:
        print("❌ 予約データ取得失敗")

def main():
    print("🧪 HALLEL渋谷店予約システム Vercel本番テスト")
    print("=" * 50)

    # 1. 現在の予約状況確認
    print("\n1. 現在の予約状況:")
    check_reservations()

    # 2. ログイン
    print("\n2. 管理者ログイン:")
    session = login_and_get_session()

    if not session:
        print("❌ テスト中断: ログインに失敗しました")
        return

    # 3. 手動予約追加テスト
    print("\n3. 手動予約追加テスト:")
    manual_success = test_add_manual_reservation(session)

    # 4. Gmail同期テスト
    print("\n4. Gmail同期テスト:")
    gmail_success = test_gmail_sync(session)

    # 5. 結果確認
    print("\n5. テスト後の予約状況:")
    check_reservations()

    # 結果サマリー
    print("\n" + "=" * 50)
    print("📋 テスト結果サマリー:")
    print(f"✅ 手動予約追加: {'成功' if manual_success else '失敗'}")
    print(f"✅ Gmail同期: {'成功' if gmail_success else '失敗'}")

if __name__ == "__main__":
    main()