import re
import os
import json
from datetime import datetime
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import base64

# 予約分類器をインポート
from reservation_classifier import HALLELReservationClassifier
# ラベル管理をインポート
from gmail_labeler import GmailLabeler

class GmailReservationParser:
    def __init__(self):
        self.SCOPES = [
            'https://www.googleapis.com/auth/gmail.readonly',
            'https://www.googleapis.com/auth/gmail.labels'  # ラベル操作のみに最小化
        ]
        self.service = None
        self.classifier = HALLELReservationClassifier()
        self.labeler = None  # 後で初期化
        self.setup_gmail_service()

    def setup_gmail_service(self):
        """Gmail API サービスを設定"""
        creds = None

        # Vercel環境では環境変数からトークンを取得
        token_data = os.environ.get('GMAIL_TOKEN_JSON')
        if token_data:
            try:
                token_info = json.loads(token_data)
                creds = Credentials.from_authorized_user_info(token_info, self.SCOPES)
            except Exception as e:
                print(f"環境変数からのトークン読み込みエラー: {e}")

        # ローカル環境ではファイルから読み込み
        if not creds and os.path.exists('token.json'):
            creds = Credentials.from_authorized_user_file('token.json', self.SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    print(f"トークンの更新に失敗: {e}")
                    # Vercel環境ではインタラクティブな認証は不可能
                    if os.environ.get('VERCEL_ENV'):
                        raise Exception("Vercel環境でトークンが無効です。新しいトークンを生成して環境変数に設定してください。")
                    else:
                        creds = None

            # インタラクティブ認証はローカル環境でのみ実行
            if not creds and not os.environ.get('VERCEL_ENV'):
                # 環境変数から認証情報を取得
                credentials_data = os.environ.get('GMAIL_CREDENTIALS_JSON')
                if credentials_data:
                    try:
                        credentials_info = json.loads(credentials_data)
                        flow = InstalledAppFlow.from_client_config(credentials_info, self.SCOPES)
                        creds = flow.run_local_server(port=0)
                    except Exception as e:
                        print(f"環境変数からの認証情報読み込みエラー: {e}")
                        return None
                elif os.path.exists('credentials.json'):
                    flow = InstalledAppFlow.from_client_secrets_file('credentials.json', self.SCOPES)
                    creds = flow.run_local_server(port=0)
                else:
                    print("credentials.json が見つかりません。Google Cloud Console で Gmail API を有効にし、認証情報をダウンロードしてください。")
                    return None
            elif not creds and os.environ.get('VERCEL_ENV'):
                # Vercel環境で有効なクレデンシャルがない場合
                raise Exception("Vercel環境でGmail認証に失敗しました。有効なトークンが環境変数に設定されていません。")

            # ローカル環境でのみファイルに保存
            if not os.environ.get('VERCEL_ENV') and creds:
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())

        self.service = build('gmail', 'v1', credentials=creds)

        # ラベル管理を初期化
        if self.service:
            try:
                self.labeler = GmailLabeler()
                if self.labeler.service:
                    print("✅ Gmailラベル機能が利用可能です")
            except Exception as e:
                print(f"⚠️ ラベル機能の初期化に失敗: {e}")
                self.labeler = None

        return self.service

    def get_recent_emails(self, query='subject:予約 OR subject:booking OR subject:reservation', max_results=50):
        """最近の予約関連メールを取得"""
        if not self.service:
            return []

        try:
            results = self.service.users().messages().list(
                userId='me', q=query, maxResults=max_results).execute()
            messages = results.get('messages', [])
            return messages
        except Exception as e:
            print(f"メール取得エラー: {e}")
            return []

    def get_email_content(self, message_id):
        """メールの内容を取得"""
        if not self.service:
            return None

        try:
            message = self.service.users().messages().get(userId='me', id=message_id).execute()

            # メール本文を取得
            payload = message['payload']
            body = ""

            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/plain':
                        if 'data' in part['body']:
                            body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                            break
            else:
                if payload['mimeType'] == 'text/plain' and 'data' in payload['body']:
                    body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')

            # ヘッダーから件名と送信者を取得
            headers = payload.get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            sender = next((h['value'] for h in headers if h['name'] == 'From'), '')

            return {
                'subject': subject,
                'sender': sender,
                'body': body,
                'message_id': message_id
            }

        except Exception as e:
            print(f"メール内容取得エラー: {e}")
            return None

    def parse_reservation_info(self, email_content):
        """メール内容から予約情報を解析"""
        if not email_content:
            return None

        body = email_content['body']
        subject = email_content['subject']

        # キャンセルメールかどうかをチェック
        is_cancellation = any(word in subject.lower() + body.lower() for word in [
            'cancel', 'cancellation', 'キャンセル', 'きゃんせる', '取消', '削除', '中止'
        ])

        # 日付パターン (YYYY/MM/DD, YYYY-MM-DD, MM/DD, MM月DD日など)
        date_patterns = [
            r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # 2025/09/24, 2025-09-24
            r'(\d{1,2})[/-](\d{1,2})',             # 09/24, 9/24
            r'(\d{1,2})月(\d{1,2})日',               # 9月24日
        ]

        # 時間パターン (HH:MM, HH時MM分など)
        time_patterns = [
            r'(\d{1,2}):(\d{2})',                  # 14:00
            r'(\d{1,2})時(\d{1,2})分?',             # 14時00分, 14時
        ]

        # 予約タイプの推定
        reservation_type = 'gmail'  # デフォルト
        if any(word in subject.lower() + body.lower() for word in ['charter', 'チャーター', '貸切', '貸し切り']):
            reservation_type = 'charter'

        # 日付を解析
        date_found = None
        for pattern in date_patterns:
            matches = re.findall(pattern, body)
            if matches:
                match = matches[0]
                if len(match) == 3:  # YYYY/MM/DD形式
                    year, month, day = match
                    date_found = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                elif len(match) == 2:  # MM/DD形式
                    month, day = match
                    current_year = datetime.now().year
                    date_found = f"{current_year}-{month.zfill(2)}-{day.zfill(2)}"
                break

        # 時間を解析
        times_found = []
        for pattern in time_patterns:
            matches = re.findall(pattern, body)
            for match in matches:
                if len(match) == 2:
                    hour, minute = match
                    time_str = f"{hour.zfill(2)}:{minute.zfill(2)}"
                    times_found.append(time_str)

        if date_found and times_found:
            # 開始時間と終了時間を推定（2つの時間が見つかった場合）
            start_time = times_found[0]
            end_time = times_found[1] if len(times_found) > 1 else None

            # 終了時間が見つからない場合は開始時間から1.5時間後と仮定
            if not end_time:
                start_hour = int(start_time.split(':')[0])
                start_minute = int(start_time.split(':')[1])
                end_hour = start_hour + 1
                end_minute = start_minute + 30
                if end_minute >= 60:
                    end_hour += 1
                    end_minute -= 60
                end_time = f"{end_hour:02d}:{end_minute:02d}"

            # メール本文から「〇〇様」を抽出
            customer_name = self.extract_customer_name(body)

            return {
                'date': date_found,
                'start': start_time,
                'end': end_time,
                'type': reservation_type,
                'source': 'gmail_auto',
                'email_subject': subject,
                'message_id': email_content['message_id'],
                'sender': email_content['sender'],
                'customer_name': customer_name,  # 抽出した顧客名
                'is_cancellation': is_cancellation,
                'action': 'cancel' if is_cancellation else 'book',
                'raw_body': body[:200] + '...' if len(body) > 200 else body  # 詳細用に本文の一部を保存
            }

        return None

    def extract_customer_name(self, body):
        """メール本文から顧客名（〇〇様）を抽出"""
        if not body:
            return 'N/A'

        # HALLELの予約完了メール特有のパターンを最優先で検索
        # より具体的にライン単位で処理
        lines = body.split('\n')
        for i, line in enumerate(lines):
            if line.strip() == 'より、ご予約をいただきました。' or line.strip() == 'より、ご予約をいただきました':
                # "より、ご予約を..."の前の行を探す
                for j in range(i-1, -1, -1):
                    prev_line = lines[j].strip()
                    if prev_line and not prev_line.endswith('メール') and len(prev_line) <= 20:
                        # 日本語文字（ひらがな、カタカナ、漢字）、アルファベット、スペースのみで構成されているかチェック
                        if re.match(r'^[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\u3000-\u303Fa-zA-Z\s]+$', prev_line):
                            if (not any(word in prev_line.lower() for word in ['@', 'http', 'www', '.com', '.jp', 'hallel', 'メール', 'ご予約']) and
                                not prev_line.isdigit()):
                                return prev_line
                        break

        # 正規表現による従来のパターンマッチング（フォールバック）
        hallel_patterns = [
            r'メール\n\n([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\s]+?)\n\nより、ご予約をいただきました',
            r'メール\s*\n\s*([\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\s]+?)\s*\n\s*より、ご予約をいただきました',
        ]

        # HALLELパターンを最初にチェック
        for pattern in hallel_patterns:
            matches = re.findall(pattern, body)
            if matches:
                name = matches[0].strip()
                # 明らかに名前でないものを除外
                if (len(name) >= 1 and len(name) <= 15 and
                    not any(word in name.lower() for word in ['@', 'http', 'www', '.com', '.jp', 'hallel', 'メール', 'ご予約', 'より']) and
                    not name.isdigit()):
                    return name

        # 従来の汎用パターン
        general_patterns = [
            r'([^\s\n]{1,20})様',  # 〇〇様
            r'([^\s\n]{1,20})さま',  # 〇〇さま
            r'([^\s\n]{1,20})サマ',  # 〇〇サマ
            r'お名前[：:]\s*([^\s\n]{1,20})',  # お名前: 〇〇
            r'氏名[：:]\s*([^\s\n]{1,20})',  # 氏名: 〇〇
            r'予約者[：:]\s*([^\s\n]{1,20})',  # 予約者: 〇〇
        ]

        for pattern in general_patterns:
            matches = re.findall(pattern, body)
            if matches:
                # 最初に見つかった名前を返す（一番可能性が高い）
                name = matches[0].strip()
                # 明らかに名前でないものを除外
                if len(name) >= 1 and not any(char in name for char in ['@', 'http', 'www', '.com', '.jp']):
                    return name

        return 'N/A'

    def fetch_and_parse_reservations(self):
        """新しい予約メールを取得・解析（改良版）"""
        print("Gmail から予約メールを取得中...")

        messages = self.get_recent_emails('subject:hallel OR subject:HALLEL OR from:@hacomono.jp')
        reservations = []

        for message in messages[:20]:  # 最新20件をチェック
            email_content = self.get_email_content(message['id'])
            if not email_content:
                continue

            # 新しい分類器を使用
            reservation_info = self.classifier.classify_email(
                email_content['subject'],
                email_content['body']
            )

            if reservation_info and reservation_info.confidence > 0.7:
                # 形式を従来のシステムに合わせて変換
                reservation_data = {
                    'action_type': reservation_info.action_type,
                    'date': reservation_info.date,
                    'start': reservation_info.start_time,
                    'end': reservation_info.end_time,
                    'customer_name': reservation_info.customer_name,
                    'studio': reservation_info.studio,
                    'source': 'gmail_auto',
                    'confidence': reservation_info.confidence,
                    'message_id': message['id'],
                    'email_subject': email_content['subject']
                }

                reservations.append(reservation_data)
                action_str = "予約" if reservation_info.action_type == 'booking' else "キャンセル"
                print(f"🎯 {action_str}情報を検出: {reservation_info.date} {reservation_info.start_time}-{reservation_info.end_time} ({reservation_info.customer_name}) 信頼度:{reservation_info.confidence:.2f}")

                # 処理済みメールにラベルを追加
                if self.labeler:
                    self.labeler.label_processed_reservation(
                        message['id'],
                        reservation_info.action_type,
                        reservation_info.customer_name
                    )

        return reservations

    def fetch_and_parse_reservations_legacy(self):
        """従来の予約メール解析（後方互換性用）"""
        print("Gmail から予約メールを取得中...")

        messages = self.get_recent_emails()
        reservations = []

        for message in messages[:10]:  # 最新10件をチェック
            email_content = self.get_email_content(message['id'])
            reservation_info = self.parse_reservation_info(email_content)

            if reservation_info:
                reservations.append(reservation_info)
                print(f"予約情報を検出: {reservation_info['date']} {reservation_info['start']}-{reservation_info['end']}")

        return reservations

# テスト用の関数
def test_gmail_parser():
    parser = GmailReservationParser()
    if parser.service:
        reservations = parser.fetch_and_parse_reservations()
        print(f"検出された予約: {len(reservations)}件")
        for reservation in reservations:
            print(json.dumps(reservation, ensure_ascii=False, indent=2))
    else:
        print("Gmail API の認証に失敗しました。")

if __name__ == '__main__':
    test_gmail_parser()