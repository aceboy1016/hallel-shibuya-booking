#!/usr/bin/env python3
import os
import json
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

class GmailLabeler:
    """Gmail ラベル管理クラス"""

    def __init__(self):
        self.SCOPES = [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.labels'  # ラベル操作のみに最小化
        ]
        self.service = None
        self.setup_gmail_service()

        # HALLEL予約システム用のラベル名
        self.PROCESSED_LABEL = 'HALLEL/Processed'
        self.BOOKING_LABEL = 'HALLEL/Booking'
        self.CANCELLATION_LABEL = 'HALLEL/Cancellation'
        self.SHIBUYA_LABEL = 'HALLEL/Shibuya'

    def setup_gmail_service(self):
        """Gmail API サービスを設定"""
        creds = None

        # ローカル環境ではファイルから読み込み
        if os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                return None

        self.service = build('gmail', 'v1', credentials=creds)
        return self.service

    def create_label_if_not_exists(self, label_name):
        """ラベルが存在しない場合は作成"""
        try:
            # 既存ラベルを取得
            results = self.service.users().labels().list(userId='me').execute()
            labels = results.get('labels', [])

            # ラベルが存在するかチェック
            for label in labels:
                if label['name'] == label_name:
                    return label['id']

            # ラベルが存在しない場合は作成
            label_object = {
                'name': label_name,
                'labelListVisibility': 'labelShow',
                'messageListVisibility': 'show'
            }

            created_label = self.service.users().labels().create(
                userId='me', body=label_object).execute()

            print(f"✅ ラベル作成: {label_name}")
            return created_label['id']

        except Exception as e:
            print(f"❌ ラベル作成エラー: {label_name} - {e}")
            return None

    def add_label_to_message(self, message_id, label_name):
        """メッセージにラベルを追加"""
        try:
            # ラベルIDを取得
            label_id = self.create_label_if_not_exists(label_name)
            if not label_id:
                return False

            # メッセージにラベルを追加
            self.service.users().messages().modify(
                userId='me',
                id=message_id,
                body={'addLabelIds': [label_id]}
            ).execute()

            return True

        except Exception as e:
            print(f"❌ ラベル追加エラー: {message_id} - {e}")
            return False

    def label_processed_reservation(self, message_id, action_type, customer_name):
        """処理済み予約メールにラベルを追加"""
        print(f"🏷️ ラベル追加中: {customer_name} ({action_type})")

        # 基本ラベル
        success = self.add_label_to_message(message_id, self.PROCESSED_LABEL)
        success &= self.add_label_to_message(message_id, self.SHIBUYA_LABEL)

        # アクションタイプ別ラベル
        if action_type == 'booking':
            success &= self.add_label_to_message(message_id, self.BOOKING_LABEL)
        elif action_type == 'cancellation':
            success &= self.add_label_to_message(message_id, self.CANCELLATION_LABEL)

        if success:
            print(f"✅ ラベル追加完了: {customer_name}")
        else:
            print(f"❌ ラベル追加失敗: {customer_name}")

        return success

    def get_unlabeled_hallel_messages(self):
        """未処理のHALLELメッセージを取得"""
        try:
            # HALLEL関連で未処理のメッセージを検索
            query = 'from:hallel -label:HALLEL/Processed'

            results = self.service.users().messages().list(
                userId='me', q=query, maxResults=50).execute()

            messages = results.get('messages', [])
            print(f"🔍 未処理HALLEL メッセージ: {len(messages)}件")

            return messages

        except Exception as e:
            print(f"❌ メッセージ検索エラー: {e}")
            return []

    def setup_initial_labels(self):
        """初期ラベルセットアップ"""
        labels_to_create = [
            self.PROCESSED_LABEL,
            self.BOOKING_LABEL,
            self.CANCELLATION_LABEL,
            self.SHIBUYA_LABEL
        ]

        print("🏷️ 初期ラベルセットアップ中...")
        for label_name in labels_to_create:
            self.create_label_if_not_exists(label_name)
        print("✅ 初期ラベルセットアップ完了")

def test_labeler():
    """ラベル機能のテスト"""
    labeler = GmailLabeler()

    if not labeler.service:
        print("❌ Gmail接続に失敗しました")
        return

    print("🧪 Gmailラベラーテスト開始")

    # 初期ラベルセットアップ
    labeler.setup_initial_labels()

    # 未処理メッセージを取得
    unlabeled_messages = labeler.get_unlabeled_hallel_messages()

    print(f"📋 処理対象メッセージ: {len(unlabeled_messages)}件")

if __name__ == "__main__":
    test_labeler()