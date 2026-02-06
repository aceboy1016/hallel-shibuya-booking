#!/usr/bin/env python3
"""
Vercel環境変数自動設定スクリプト
Gmail認証情報とシークレットキーをVercelに設定
"""

import os
import json
import subprocess
import secrets
import tempfile

def run_command(cmd, input_text=None):
    """コマンドを実行"""
    try:
        if input_text:
            result = subprocess.run(cmd, shell=True, input=input_text,
                                  text=True, capture_output=True)
        else:
            result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        return result.returncode == 0, result.stdout, result.stderr
    except Exception as e:
        return False, "", str(e)

def set_vercel_env_var(name, value):
    """Vercel環境変数を設定"""
    print(f"🔧 環境変数 {name} を設定中...")

    # 一時ファイルに値を書き込み
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as tmp:
        tmp.write(value)
        tmp_path = tmp.name

    try:
        # Vercel CLIで環境変数を設定
        cmd = f'cat "{tmp_path}" | vercel env add {name} production'
        success, stdout, stderr = run_command(cmd)

        if success:
            print(f"✅ {name} 設定完了")
        else:
            print(f"❌ {name} 設定失敗: {stderr}")
            return False
    finally:
        # 一時ファイルを削除
        os.unlink(tmp_path)

    return success

def setup_vercel_environment():
    """Vercel環境変数を設定"""
    print("🚀 HALLEL渋谷店予約システム - Vercel環境変数設定")
    print("=" * 60)

    # 1. SECRET_KEY生成・設定
    print("\\n1. SECRET_KEY 生成・設定:")
    secret_key = secrets.token_hex(32)
    if not set_vercel_env_var("SECRET_KEY", secret_key):
        return False

    # 2. GMAIL_CREDENTIALS_JSON設定
    print("\\n2. GMAIL_CREDENTIALS_JSON 設定:")
    if os.path.exists('credentials.json'):
        with open('credentials.json', 'r') as f:
            credentials_json = f.read()
        if not set_vercel_env_var("GMAIL_CREDENTIALS_JSON", credentials_json):
            return False
    else:
        print("❌ credentials.json が見つかりません")
        return False

    # 3. GMAIL_TOKEN_JSON設定
    print("\\n3. GMAIL_TOKEN_JSON 設定:")
    if os.path.exists('token.json'):
        with open('token.json', 'r') as f:
            token_json = f.read()
        if not set_vercel_env_var("GMAIL_TOKEN_JSON", token_json):
            return False
    else:
        print("❌ token.json が見つかりません")
        return False

    print("\\n" + "=" * 60)
    print("✅ 全ての環境変数設定が完了しました！")
    print("🔄 新しいデプロイメントで環境変数が有効になります")

    return True

def deploy_with_env_vars():
    """環境変数設定後にデプロイ"""
    print("\\n🚀 本番環境に再デプロイ中...")
    success, stdout, stderr = run_command("vercel --prod")

    if success:
        print("✅ デプロイ完了")
        # URLを抽出
        lines = stdout.split('\\n')
        for line in lines:
            if 'https://' in line and 'vercel.app' in line:
                print(f"🌐 本番URL: {line}")
                return line.strip()
    else:
        print(f"❌ デプロイ失敗: {stderr}")

    return None

def test_gmail_sync(url):
    """Gmail同期をテスト"""
    if not url:
        return False

    print(f"\\n🧪 Gmail同期テスト: {url}")

    # requests を使用してテスト
    try:
        import requests
        session = requests.Session()

        # ログイン
        login_data = {"password": "hallel"}
        login_response = session.post(f"{url}/login", data=login_data)

        if login_response.status_code in [200, 302]:
            # Gmail同期テスト
            sync_response = session.post(f"{url}/api/gmail/sync")

            if sync_response.status_code == 200:
                print("✅ Gmail同期テスト成功")
                data = sync_response.json()
                print(f"📊 結果: {data.get('message', 'N/A')}")
                return True
            else:
                print(f"❌ Gmail同期テスト失敗: {sync_response.status_code}")
                print(f"エラー: {sync_response.text}")
        else:
            print("❌ ログインテスト失敗")
    except ImportError:
        print("⚠️ requests モジュールがないため、手動テストしてください")
    except Exception as e:
        print(f"❌ テストエラー: {e}")

    return False

def main():
    """メイン実行関数"""
    print("🎯 HALLEL渋谷店予約システム完全セットアップ")
    print("=" * 60)

    # 1. 環境変数設定
    if not setup_vercel_environment():
        print("❌ セットアップ失敗")
        return

    # 2. デプロイ
    url = deploy_with_env_vars()

    # 3. テスト
    if url:
        test_gmail_sync(url)

    print("\\n" + "=" * 60)
    print("🎉 HALLEL渋谷店予約システム セットアップ完了！")
    print("\\n📱 使用方法:")
    print(f"1. {url or 'https://hallelshibuyabooking.vercel.app'} にアクセス")
    print("2. 管理画面: /admin (パスワード: hallel)")
    print("3. Gmail同期ボタンをクリックしてテスト")

if __name__ == "__main__":
    main()