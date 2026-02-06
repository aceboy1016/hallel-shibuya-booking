import re
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, Dict, Any

@dataclass
class ReservationInfo:
    """予約情報を格納するデータクラス"""
    action_type: str  # 'booking' or 'cancellation'
    date: str  # YYYY-MM-DD
    start_time: str  # HH:MM
    end_time: str  # HH:MM
    customer_name: str
    studio: str
    duration_minutes: int
    confidence: float  # 0.0-1.0の信頼度
    raw_text: str

class HALLELReservationClassifier:
    """HALLEL予約メール分類器"""

    def __init__(self):
        # 予約完了のキーワード
        self.booking_keywords = [
            "ご予約ありがとうございます",
            "以下の内容を承りました",
            "ご確認ください",
            "予約が完了",
            "承りました"
        ]

        # キャンセルのキーワード
        self.cancellation_keywords = [
            "キャンセルいたしました",
            "予約をキャンセル",
            "キャンセルしました",
            "取り消し",
            "キャンセル完了"
        ]

        # 日時パターン
        self.date_pattern = r'(\d{4})年(\d{1,2})月(\d{1,2})日'
        self.time_pattern = r'(\d{1,2}):(\d{2})~(\d{1,2}):(\d{2})'
        self.customer_pattern = r'(.*?)\s*様'

    def classify_email(self, subject: str, body: str) -> Optional[ReservationInfo]:
        """
        メールを分析して予約情報を抽出・分類

        Args:
            subject: メール件名
            body: メール本文

        Returns:
            ReservationInfo: 分析結果、分類できない場合はNone
        """
        try:
            # HALLELメールかどうかチェック
            if not self._is_hallel_email(subject, body):
                return None

            # アクションタイプを判定
            action_type = self._determine_action_type(body)
            if not action_type:
                return None

            # 顧客名を抽出
            customer_name = self._extract_customer_name(body)

            # 日時を抽出
            date_info = self._extract_date_time(body)
            if not date_info:
                return None

            # スタジオ情報を抽出
            studio_info = self._extract_studio_info(body)

            # 信頼度を計算
            confidence = self._calculate_confidence(action_type, body)

            return ReservationInfo(
                action_type=action_type,
                date=date_info['date'],
                start_time=date_info['start_time'],
                end_time=date_info['end_time'],
                customer_name=customer_name,
                studio=studio_info,
                duration_minutes=date_info['duration'],
                confidence=confidence,
                raw_text=body
            )

        except Exception as e:
            print(f"メール分類エラー: {e}")
            return None

    def _is_hallel_email(self, subject: str, body: str) -> bool:
        """HALLELからのメールかどうか判定（渋谷店限定）"""
        # まずHALLELメールかチェック
        hallel_indicators = [
            "HALLEL",
            "hallel"
        ]

        combined_text = f"{subject} {body}".lower()
        is_hallel = any(indicator.lower() in combined_text for indicator in hallel_indicators)

        if not is_hallel:
            return False

        # 渋谷店のメールかチェック（半蔵門店を除外）
        if "半蔵門店" in body or "hanzomon" in body.lower():
            return False

        # 渋谷店であることを確認
        if "渋谷店" in body or "shibuya" in body.lower():
            return True

        # 明示的に店舗情報がない場合は保留（要検討）
        return False

    def _determine_action_type(self, body: str) -> Optional[str]:
        """予約かキャンセルかを判定"""
        body_lower = body.lower()

        # キャンセルキーワードのチェック（優先度高）
        for keyword in self.cancellation_keywords:
            if keyword in body:
                return 'cancellation'

        # 予約完了キーワードのチェック
        for keyword in self.booking_keywords:
            if keyword in body:
                return 'booking'

        # 件名でも判定
        if 'キャンセル' in body or 'cancel' in body_lower:
            return 'cancellation'
        elif '予約' in body and ('ありがとう' in body or '承り' in body):
            return 'booking'

        return None

    def _extract_customer_name(self, body: str) -> str:
        """顧客名を抽出"""
        match = re.search(self.customer_pattern, body)
        if match:
            name = match.group(1).strip()
            # "辻 克哉" のような形式
            return name
        return "不明"

    def _extract_date_time(self, body: str) -> Optional[Dict[str, Any]]:
        """日時情報を抽出"""
        # 日付を抽出
        date_match = re.search(self.date_pattern, body)
        if not date_match:
            return None

        year = int(date_match.group(1))
        month = int(date_match.group(2))
        day = int(date_match.group(3))

        # 時間を抽出
        time_match = re.search(self.time_pattern, body)
        if not time_match:
            return None

        start_hour = int(time_match.group(1))
        start_minute = int(time_match.group(2))
        end_hour = int(time_match.group(3))
        end_minute = int(time_match.group(4))

        # 形式を統一
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        start_time = f"{start_hour:02d}:{start_minute:02d}"
        end_time = f"{end_hour:02d}:{end_minute:02d}"

        # 利用時間を計算
        start_minutes = start_hour * 60 + start_minute
        end_minutes = end_hour * 60 + end_minute
        duration = end_minutes - start_minutes

        return {
            'date': date_str,
            'start_time': start_time,
            'end_time': end_time,
            'duration': duration
        }

    def _extract_studio_info(self, body: str) -> str:
        """スタジオ情報を抽出"""
        # "渋谷店 STUDIO ⑥ (1)" のようなパターン
        studio_pattern = r'(渋谷店\s*STUDIO\s*[⑥①②③④⑤⑦⑧⑨⑩]*\s*\(\d+\))'
        match = re.search(studio_pattern, body)
        if match:
            return match.group(1).strip()

        # より簡単なパターン
        if "STUDIO" in body:
            return "STUDIO"

        return "不明"

    def _calculate_confidence(self, action_type: str, body: str) -> float:
        """信頼度を計算（0.0-1.0）"""
        confidence = 0.5  # ベース信頼度

        # キーワードマッチングによる信頼度向上
        if action_type == 'booking':
            for keyword in self.booking_keywords:
                if keyword in body:
                    confidence += 0.1
        elif action_type == 'cancellation':
            for keyword in self.cancellation_keywords:
                if keyword in body:
                    confidence += 0.15

        # 構造化された情報の存在確認
        if re.search(self.date_pattern, body):
            confidence += 0.1
        if re.search(self.time_pattern, body):
            confidence += 0.1
        if "HALLEL" in body:
            confidence += 0.1

        return min(confidence, 1.0)

    def test_classification(self, test_emails: list) -> None:
        """テスト用メソッド"""
        for i, (subject, body) in enumerate(test_emails):
            print(f"\n=== テストメール {i+1} ===")
            result = self.classify_email(subject, body)
            if result:
                print(f"アクション: {result.action_type}")
                print(f"日時: {result.date} {result.start_time}-{result.end_time}")
                print(f"顧客: {result.customer_name}")
                print(f"スタジオ: {result.studio}")
                print(f"信頼度: {result.confidence:.2f}")
            else:
                print("分類できませんでした")