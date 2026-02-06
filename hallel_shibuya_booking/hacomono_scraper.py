from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import logging
from datetime import datetime, timedelta
import re

class HacomonoScraper:
    def __init__(self):
        self.driver = None
        self.wait = None
        self.setup_logging()

    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('hacomono_scraper.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def setup_driver(self, headless=True):
        """Chrome WebDriverをセットアップ"""
        try:
            chrome_options = Options()
            if headless:
                chrome_options.add_argument("--headless")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")

            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            self.wait = WebDriverWait(self.driver, 10)

            self.logger.info("WebDriver セットアップ完了")
            return True

        except Exception as e:
            self.logger.error(f"WebDriver セットアップ失敗: {e}")
            return False

    def login(self, email, password, login_url="https://www.hacomono.jp/login"):
        """hacomonoにログイン"""
        try:
            self.logger.info("hacomonoにログイン中...")
            self.driver.get(login_url)

            # メールアドレス入力
            email_field = self.wait.until(
                EC.presence_of_element_located((By.NAME, "email"))
            )
            email_field.send_keys(email)

            # パスワード入力
            password_field = self.driver.find_element(By.NAME, "password")
            password_field.send_keys(password)

            # ログインボタンクリック
            login_button = self.driver.find_element(By.XPATH, "//button[@type='submit']")
            login_button.click()

            # ログイン成功を確認（ダッシュボード画面への遷移を待つ）
            self.wait.until(EC.url_contains("dashboard"))
            self.logger.info("ログイン成功")
            return True

        except Exception as e:
            self.logger.error(f"ログイン失敗: {e}")
            return False

    def select_store(self, store_name="半蔵門店"):
        """特定の店舗を選択"""
        try:
            self.logger.info(f"店舗を選択中: {store_name}")

            # 店舗選択ドロップダウンまたはタブを探す
            store_selectors = [
                (By.XPATH, f"//select[@name='store']//option[contains(text(), '{store_name}')]"),
                (By.XPATH, f"//div[contains(@class, 'store-selector')]//span[contains(text(), '{store_name}')]"),
                (By.XPATH, f"//a[contains(@class, 'store-tab')][contains(text(), '{store_name}')]"),
                (By.XPATH, f"//button[contains(text(), '{store_name}')]"),
                (By.LINK_TEXT, store_name),
                (By.PARTIAL_LINK_TEXT, store_name)
            ]

            for selector_type, selector in store_selectors:
                try:
                    store_element = self.wait.until(EC.element_to_be_clickable((selector_type, selector)))
                    store_element.click()
                    self.logger.info(f"店舗選択成功: {store_name}")
                    time.sleep(2)  # 店舗切り替え待機
                    return True
                except:
                    continue

            # 店舗選択要素が見つからない場合の代替手段
            self.logger.warning(f"店舗選択要素が見つかりません。URL直接指定を試行中...")

            # 店舗IDを含むURLパターンを試す
            store_patterns = {
                "半蔵門店": ["hanzomon", "hanzomonten", "hanzoumon"],
                "渋谷店": ["shibuya", "shibuyaten"],
                "新宿店": ["shinjuku", "shinjukuten"],
                "池袋店": ["ikebukuro", "ikebukuroten"],
                "銀座店": ["ginza", "ginzaten"]
            }

            if store_name in store_patterns:
                for pattern in store_patterns[store_name]:
                    try:
                        store_url = f"https://admin.hacomono.jp/stores/{pattern}/dashboard"
                        self.driver.get(store_url)
                        time.sleep(3)

                        # 正しいページに移動できたかチェック
                        if store_name.replace("店", "") in self.driver.page_source:
                            self.logger.info(f"URL直接指定で店舗選択成功: {store_name}")
                            return True
                    except:
                        continue

            self.logger.error(f"店舗選択失敗: {store_name}")
            return False

        except Exception as e:
            self.logger.error(f"店舗選択エラー: {e}")
            return False

    def navigate_to_schedule(self, date=None, store_name="半蔵門店"):
        """スケジュール画面に遷移"""
        try:
            if date is None:
                date = datetime.now().strftime("%Y-%m-%d")

            # まず店舗を選択
            if not self.select_store(store_name):
                self.logger.warning("店舗選択に失敗しましたが、処理を続行します")

            # スケジュール画面のURLを構築（複数のパターンを試行）
            schedule_urls = [
                f"https://admin.hacomono.jp/schedule?date={date}",
                f"https://admin.hacomono.jp/reservations?date={date}",
                f"https://admin.hacomono.jp/calendar?date={date}",
            ]

            for schedule_url in schedule_urls:
                try:
                    self.driver.get(schedule_url)
                    time.sleep(3)

                    # ページ読み込み待機（複数のパターンを試行）
                    page_indicators = [
                        (By.CLASS_NAME, "schedule-container"),
                        (By.CLASS_NAME, "calendar-container"),
                        (By.CLASS_NAME, "reservation-list"),
                        (By.XPATH, "//div[contains(@class, 'schedule')]"),
                        (By.XPATH, "//table[contains(@class, 'calendar')]")
                    ]

                    for indicator_type, indicator in page_indicators:
                        try:
                            self.wait.until(EC.presence_of_element_located((indicator_type, indicator)))
                            self.logger.info(f"スケジュール画面に遷移成功: {date} ({store_name})")
                            return True
                        except:
                            continue

                except Exception as e:
                    self.logger.warning(f"URL {schedule_url} でのアクセス失敗: {e}")
                    continue

            self.logger.error(f"すべてのスケジュールURLでアクセス失敗")
            return False

        except Exception as e:
            self.logger.error(f"スケジュール画面遷移失敗: {e}")
            return False

    def extract_reservations(self, target_date=None):
        """予約情報を抽出"""
        try:
            if target_date is None:
                target_date = datetime.now().strftime("%Y-%m-%d")

            reservations = []

            # 予約枠要素を取得（実際のhacomonoのHTML構造に合わせて調整が必要）
            reservation_elements = self.driver.find_elements(
                By.CLASS_NAME, "reservation-slot"
            )

            for element in reservation_elements:
                try:
                    # 時間の抽出
                    time_element = element.find_element(By.CLASS_NAME, "time-slot")
                    time_text = time_element.text.strip()

                    # 状態の確認（ブロック、予約済み、など）
                    status_element = element.find_element(By.CLASS_NAME, "status")
                    status = status_element.text.strip()

                    # 予約者情報（あれば）
                    customer_info = ""
                    try:
                        customer_element = element.find_element(By.CLASS_NAME, "customer-name")
                        customer_info = customer_element.text.strip()
                    except:
                        pass

                    # 時間をstart/endに分割
                    if "～" in time_text or "-" in time_text:
                        separator = "～" if "～" in time_text else "-"
                        start_time, end_time = time_text.split(separator)
                        start_time = start_time.strip()
                        end_time = end_time.strip()
                    else:
                        # 単一時間の場合は1時間と仮定
                        start_time = time_text.strip()
                        end_time = self._add_hour(start_time)

                    reservation = {
                        'date': target_date,
                        'start': start_time,
                        'end': end_time,
                        'type': self._determine_type(status),
                        'status': status,
                        'customer_name': customer_info if customer_info else 'N/A',
                        'source': 'hacomono_scraping'
                    }

                    reservations.append(reservation)

                except Exception as e:
                    self.logger.warning(f"予約要素の処理でエラー: {e}")
                    continue

            self.logger.info(f"抽出完了: {len(reservations)}件の予約")
            return reservations

        except Exception as e:
            self.logger.error(f"予約抽出失敗: {e}")
            return []

    def _determine_type(self, status):
        """ステータスから予約タイプを判定"""
        status_lower = status.lower()
        if 'ブロック' in status or 'block' in status_lower:
            return 'block'
        elif '貸切' in status or 'charter' in status_lower:
            return 'charter'
        elif '予約' in status or 'booking' in status_lower:
            return 'gmail'  # 通常予約
        else:
            return 'unknown'

    def _add_hour(self, time_str):
        """時間に1時間を追加"""
        try:
            time_obj = datetime.strptime(time_str, "%H:%M")
            end_time = time_obj + timedelta(hours=1)
            return end_time.strftime("%H:%M")
        except:
            return time_str

    def fetch_reservations_for_date_range(self, start_date, end_date, email, password, store_name="半蔵門店"):
        """指定期間の予約を取得"""
        all_reservations = []

        if not self.setup_driver():
            return all_reservations

        try:
            # ログイン
            if not self.login(email, password):
                return all_reservations

            current_date = datetime.strptime(start_date, "%Y-%m-%d")
            end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")

            while current_date <= end_date_obj:
                date_str = current_date.strftime("%Y-%m-%d")

                # 各日付のスケジュール画面に遷移（店舗指定）
                if self.navigate_to_schedule(date_str, store_name):
                    # 予約情報を抽出
                    daily_reservations = self.extract_reservations(date_str)
                    # 店舗名を追加
                    for reservation in daily_reservations:
                        reservation['store_name'] = store_name
                    all_reservations.extend(daily_reservations)

                # 次の日へ
                current_date += timedelta(days=1)
                time.sleep(1)  # サーバー負荷軽減

        except Exception as e:
            self.logger.error(f"期間取得処理でエラー: {e}")

        finally:
            self.cleanup()

        return all_reservations

    def cleanup(self):
        """リソースをクリーンアップ"""
        if self.driver:
            self.driver.quit()
            self.logger.info("WebDriver クリーンアップ完了")

# テスト用の関数
def test_hacomono_scraper():
    scraper = HacomonoScraper()

    # 注意: 実際の認証情報に置き換えてください
    test_email = "your-email@example.com"
    test_password = "your-password"

    # 今日から1週間分の予約を取得
    start_date = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

    reservations = scraper.fetch_reservations_for_date_range(
        start_date, end_date, test_email, test_password
    )

    print(f"取得した予約数: {len(reservations)}")
    for reservation in reservations:
        print(f"日付: {reservation['date']}, 時間: {reservation['start']}-{reservation['end']}, "
              f"タイプ: {reservation['type']}, 顧客: {reservation['customer_name']}")

if __name__ == "__main__":
    test_hacomono_scraper()