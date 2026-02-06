#!/usr/bin/env python3
"""
高速Gmail同期処理
タイムアウト問題を解決するため軽量化
"""
import os
import json
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import base64
import re

class FastGmailSync:
    def __init__(self):
        self.SCOPES = [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.labels',  # ラベル操作
            'https://www.googleapis.com/auth/gmail.modify'   # メール修正
        ]
        self.service = None
        self.setup_gmail_service()

        # ラベル管理
        self.label_ids = {}
        self.setup_labels()

    def setup_gmail_service(self):
        """Gmail API サービスを設定（軽量版）"""
        creds = None

        # Vercel環境では環境変数からトークンを取得
        token_data = os.environ.get('GMAIL_TOKEN_JSON')
        if token_data:
            try:
                token_info = json.loads(token_data)
                creds = Credentials.from_authorized_user_info(token_info, self.SCOPES)
            except Exception as e:
                print(f"トークン読み込みエラー: {e}")
                return

        # ローカル環境ではファイルから読み込み
        if not creds and os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"トークン更新失敗: {e}")
                    return
            else:
                if os.environ.get('VERCEL_ENV'):
                    raise Exception("Vercel環境で有効なトークンがありません")
                return

        self.service = build('gmail', 'v1', credentials=creds)

    def setup_labels(self):
        """必要なラベルを作成・設定"""
        if not self.service:
            return

        labels_to_create = [
            'HALLEL/Processed',
            'HALLEL/Booking',
            'HALLEL/Cancellation',
            'HALLEL/Shibuya'
        ]

        try:
            # 既存ラベルを取得
            results = self.service.users().labels().list(userId='me').execute()
            existing_labels = {label['name']: label['id'] for label in results.get('labels', [])}

            for label_name in labels_to_create:
                if label_name in existing_labels:
                    self.label_ids[label_name] = existing_labels[label_name]
                    print(f"✅ ラベル既存: {label_name}")
                else:
                    # ラベルを作成
                    label_object = {
                        'name': label_name,
                        'labelListVisibility': 'labelShow',
                        'messageListVisibility': 'show'
                    }

                    result = self.service.users().labels().create(
                        userId='me',
                        body=label_object
                    ).execute()

                    self.label_ids[label_name] = result['id']
                    print(f"🏷️ ラベル作成: {label_name}")

        except Exception as e:
            print(f"❌ ラベル設定エラー: {e}")

    def apply_label(self, message_id, label_type):
        """メールにラベルを適用"""
        if not self.service:
            return

        try:
            # ラベルタイプに応じてラベルを選択
            labels_to_add = ['HALLEL/Processed', 'HALLEL/Shibuya']

            if label_type == 'booking':
                labels_to_add.append('HALLEL/Booking')
            elif label_type == 'cancellation':
                labels_to_add.append('HALLEL/Cancellation')

            # 実際のラベルIDを取得
            label_ids_to_add = []
            for label_name in labels_to_add:
                if label_name in self.label_ids:
                    label_ids_to_add.append(self.label_ids[label_name])

            if label_ids_to_add:
                # ラベルを適用
                body = {
                    'addLabelIds': label_ids_to_add
                }

                self.service.users().messages().modify(
                    userId='me',
                    id=message_id,
                    body=body
                ).execute()

                print(f"🏷️ ラベル適用: {', '.join(labels_to_add)}")

        except Exception as e:
            print(f"❌ ラベル適用エラー: {e}")

    def get_recent_reservations(self):
        """最近の予約メールを高速取得"""
        if not self.service:
            return []

        try:
            # 最近3日間のhacomonoメールのみを対象
            three_days_ago = (datetime.now() - timedelta(days=3)).strftime('%Y/%m/%d')
            query = f"from:noreply@em.hacomono.jp subject:hallel after:{three_days_ago}"

            print(f"🔍 検索クエリ: {query}")

            result = self.service.users().messages().list(
                userId='me',
                q=query,
                maxResults=10  # 最大10件に制限
            ).execute()

            messages = result.get('messages', [])
            print(f"📧 見つかったメール: {len(messages)}件")

            reservations = []
            for i, message in enumerate(messages):
                print(f"⏳ 処理中... ({i+1}/{len(messages)})")

                try:
                    # メッセージの詳細を取得（最小限）
                    msg = self.service.users().messages().get(
                        userId='me',
                        id=message['id'],
                        format='metadata',  # ヘッダーのみ取得で高速化
                        metadataHeaders=['Subject', 'From', 'Date']
                    ).execute()

                    # 件名と送信者を確認
                    subject = self.get_header_value(msg, 'Subject')
                    sender = self.get_header_value(msg, 'From')

                    print(f"📧 件名: {subject}")
                    print(f"👤 送信者: {sender}")

                    # HALLELの予約メールかチェック
                    if 'hallel' in subject.lower() and 'hacomono' in sender.lower():
                        # 本文を取得して詳細解析
                        full_msg = self.service.users().messages().get(
                            userId='me',
                            id=message['id']
                        ).execute()

                        body = self.extract_body(full_msg)
                        reservation = self.parse_reservation(body, subject)

                        if reservation:
                            reservation['email_id'] = message['id']
                            reservation['email_subject'] = subject
                            reservation['email_sender'] = sender
                            reservations.append(reservation)
                            print(f"✅ 予約検出: {reservation.get('date')} {reservation.get('start')}-{reservation.get('end')}")

                            # ラベルを適用
                            label_type = 'cancellation' if reservation.get('is_cancellation') else 'booking'
                            self.apply_label(message['id'], label_type)

                except Exception as e:
                    print(f"❌ メール処理エラー: {e}")
                    continue

            print(f"📊 最終結果: {len(reservations)}件の予約")
            return reservations

        except Exception as e:
            print(f"❌ Gmail検索エラー: {e}")
            return []

    def get_header_value(self, message, header_name):
        """メッセージヘッダーから値を取得"""
        headers = message['payload'].get('headers', [])
        for header in headers:
            if header['name'] == header_name:
                return header['value']
        return ''

    def extract_body(self, message):
        """メール本文を抽出（軽量版）"""
        try:
            payload = message['payload']

            # マルチパートでない場合
            if 'data' in payload.get('body', {}):
                data = payload['body']['data']
                return base64.urlsafe_b64decode(data).decode('utf-8')

            # マルチパートの場合、最初のテキスト部分を取得
            parts = payload.get('parts', [])
            for part in parts:
                if part['mimeType'] == 'text/plain' and 'data' in part.get('body', {}):
                    data = part['body']['data']
                    return base64.urlsafe_b64decode(data).decode('utf-8')

        except Exception as e:
            print(f"本文抽出エラー: {e}")

        return ""

    def parse_reservation(self, body, subject):
        """予約情報を解析（簡略版）"""
        if not body:
            return None

        try:
            print(f"🔍 本文解析中...")
            print(f"📝 本文の一部: {body[:200]}...")

            # 渋谷店フィルタ（より柔軟に）
            body_lower = body.lower()
            if not ('渋谷' in body or 'shibuya' in body_lower or 'hallel' in body_lower):
                print("❌ 渋谷店のメールではありません")
                return None

            print("✅ 渋谷店のメールを検出")

            # キャンセルかどうかチェック
            is_cancellation = 'キャンセル' in subject or 'cancel' in subject.lower()

            # 日付を抽出（複数パターンに対応）
            date_patterns = [
                r'(\d{4})年(\d{1,2})月(\d{1,2})日',  # 2025年11月02日
                r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # 2025/11/02
                r'日時：(\d{4})年(\d{1,2})月(\d{1,2})日'  # 日時：2025年11月02日
            ]

            date_match = None
            for pattern in date_patterns:
                date_match = re.search(pattern, body)
                if date_match:
                    break

            if not date_match:
                print("❌ 日付パターンが見つかりません")
                return None

            year, month, day = date_match.groups()
            date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
            print(f"📅 日付: {date}")

            # 時間を抽出（複数パターンに対応）
            time_patterns = [
                r'(\d{1,2}):(\d{2})\s*[〜～~-]\s*(\d{1,2}):(\d{2})',  # 10:00~11:00
                r'(\d{1,2}):(\d{2})～(\d{1,2}):(\d{2})',  # 10:00～11:00
                r'(\d{1,2}):(\d{2})-(\d{1,2}):(\d{2})'   # 10:00-11:00
            ]

            time_match = None
            for pattern in time_patterns:
                time_match = re.search(pattern, body)
                if time_match:
                    break

            if not time_match:
                print("❌ 時間パターンが見つかりません")
                return None

            start_hour, start_min, end_hour, end_min = time_match.groups()
            start_time = f"{start_hour.zfill(2)}:{start_min}"
            end_time = f"{end_hour.zfill(2)}:{end_min}"
            print(f"⏰ 時間: {start_time}-{end_time}")

            # 顧客名を抽出（複数パターンに対応）
            customer_patterns = [
                r'^([^\n\r]+)\s*様',  # 最初の行の「〇〇 様」
                r'(?:お名前|氏名)[：:\s]*([^\n\r]+)',  # お名前：〇〇
                r'([^\n\r]+)\s*様\s*\n\n(?:ご予約|以下の予約)'  # 〇〇 様 + 予約メッセージ
            ]

            customer_name = 'N/A'
            for pattern in customer_patterns:
                customer_match = re.search(pattern, body, re.MULTILINE)
                if customer_match:
                    customer_name = customer_match.group(1).strip()
                    # 「様」を除去
                    customer_name = customer_name.replace('様', '').strip()
                    break

            print(f"👤 顧客名: {customer_name}")

            return {
                'date': date,
                'start': start_time,
                'end': end_time,
                'customer_name': customer_name,
                'type': 'gmail',
                'is_cancellation': is_cancellation,
                'source': 'fast_gmail_sync'
            }

        except Exception as e:
            print(f"予約解析エラー: {e}")
            return None

def test_fast_sync():
    """テスト実行"""
    sync = FastGmailSync()
    if sync.service:
        reservations = sync.get_recent_reservations()
        print(f"\n📋 取得結果:")
        for res in reservations:
            print(f"- {res['date']} {res['start']}-{res['end']} {res['customer_name']}")
    else:
        print("❌ Gmail接続失敗")

if __name__ == '__main__':
    test_fast_sync()