#!/usr/bin/env python3
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

def manual_auth():
    """手動認証用のヘルパー関数"""
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']

    if not os.path.exists('credentials.json'):
        print("❌ credentials.json が見つかりません")
        return None

    try:
        # OAuth2フローを作成（デスクトップフロー）
        flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)

        # 手動認証用の認証URLを生成
        flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
        auth_url, _ = flow.authorization_url(prompt='consent')

        print("🔗 以下のURLをブラウザで開いて認証してください：")
        print(f"\n{auth_url}\n")

        # 認証コードの入力を求める
        auth_code = input("認証コードを入力してください: ").strip()

        # トークンを取得
        flow.fetch_token(code=auth_code)
        creds = flow.credentials

        # トークンを保存
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

        print("✅ 認証完了！token.json に保存されました")
        return creds

    except Exception as e:
        print(f"❌ 認証エラー: {e}")
        return None

if __name__ == "__main__":
    manual_auth()