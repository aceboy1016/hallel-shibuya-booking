from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import re
import os
import secrets
from datetime import datetime, timedelta
import logging

# 本番環境判定
is_production = os.environ.get('VERCEL_ENV') == 'production'

# 本番環境用ログ設定
if is_production:
    logging.basicConfig(level=logging.INFO)
else:
    logging.basicConfig(level=logging.DEBUG)

# Enable Gmail integration for Shibuya store
try:
    from gmail_parser import GmailReservationParser
    GMAIL_ENABLED = True
except ImportError:
    print("Gmail連携機能は利用できません。credentials.json を設定してください。")
    GMAIL_ENABLED = False

HACOMONO_ENABLED = False

# --- App Initialization ---
app = Flask(__name__)

# セキュアなSecret Key設定
secret_key = os.environ.get('SECRET_KEY')
if not secret_key:
    # 環境変数がない場合は強力なランダムキーを生成（本番環境では事前設定必須）
    secret_key = secrets.token_hex(32)
    print("⚠️ WARNING: SECRET_KEYが設定されていません。ランダムキーを生成しました。")
    print(f"SECRET_KEY={secret_key}")

app.config['SECRET_KEY'] = secret_key

# セッション設定強化
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=2)

# Vercel環境では動的にセキュリティ設定を調整
app.config['SESSION_COOKIE_SECURE'] = is_production  # 本番ではHTTPS必須
app.config['SESSION_COOKIE_HTTPONLY'] = True  # XSS対策
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # CSRF対策

# 本番環境用エラーハンドリング
@app.errorhandler(404)
def not_found(error):
    return render_template('booking-status.html'), 404

@app.errorhandler(500)
def internal_error(error):
    logging.error(f"Internal server error: {error}")
    return render_template('booking-status.html'), 500

# --- In-memory storage for Vercel (no file system access) ---
# Production admin password (from environment variable)
production_password = os.environ.get('ADMIN_PASSWORD', 'hallel')
print(f"🔍 Debug: ADMIN_PASSWORD = {production_password}")
print(f"🔍 Debug: is_production = {is_production}")

# 固定パスワードハッシュ for testing
current_password_hash = generate_password_hash('hallel', method='pbkdf2:sha256')
print(f"🔍 Debug: Using password 'hallel' with hash: {current_password_hash[:50]}...")

# Simple in-memory logging for Vercel
activity_logs = []
reservation_judgment_logs = []  # 予約メール判別専用ログ

def log_activity(action):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - Action: {action}"
    activity_logs.append(log_entry)
    # Keep only last 100 logs to prevent memory issues
    if len(activity_logs) > 100:
        activity_logs.pop(0)

def log_reservation_judgment(action_type, date, time_slot, customer_name, confidence, status="detected"):
    """予約メール判別ログを記録"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    action_emoji = "📅" if action_type == "booking" else "❌" if action_type == "cancellation" else "❓"

    # シンプルな判別ログ
    log_entry = f"{timestamp} {action_emoji} {action_type.upper()}: {customer_name} | {date} {time_slot} | 信頼度:{confidence:.2f}"

    reservation_judgment_logs.append(log_entry)

    # Keep only last 200 reservation logs
    if len(reservation_judgment_logs) > 200:
        reservation_judgment_logs.pop(0)

def get_password_hash():
    return current_password_hash

def set_password_hash(new_hash):
    global current_password_hash
    current_password_hash = new_hash


# --- In-memory database ---
reservations_db = {}

# --- Frontend Routes (Public) ---
@app.route('/')
def booking_status_page():
    return render_template('booking-status.html')

# --- Authentication Routes ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        hashed_password = get_password_hash()

        if check_password_hash(hashed_password, password):
            session['logged_in'] = True
            session['login_time'] = datetime.now().timestamp()
            session.permanent = True  # セッション有効期限を適用
            log_activity('Admin login successful')
            flash('ログインしました。', 'success')
            return redirect(url_for('admin_page'))
        else:
            log_activity('Admin login failed')
            flash('パスワードが違います。', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    log_activity('Admin logout')
    flash('ログアウトしました。', 'info')
    return redirect(url_for('login'))

# --- Admin Routes (Protected) ---
def is_logged_in():
    """セッション有効性チェック（タイムアウト機能付き）"""
    if not session.get('logged_in', False):
        return False

    # セッションタイムアウトチェック
    login_time = session.get('login_time')
    if login_time:
        elapsed_time = datetime.now().timestamp() - login_time
        if elapsed_time > app.config['PERMANENT_SESSION_LIFETIME'].total_seconds():
            session.clear()
            return False

    return True

@app.route('/admin')
def admin_page():
    if not is_logged_in():
        return redirect(url_for('login'))

    # Use reservation judgment logs for display
    logs = reservation_judgment_logs.copy()
    return render_template('admin.html', logs=reversed(logs))

@app.route('/admin/calendar')
def admin_calendar_page():
    if not is_logged_in():
        return redirect(url_for('login'))
    return render_template('admin-calendar.html')

@app.route('/admin/change_password', methods=['POST'])
def change_password():
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    new_password = request.form.get('new_password')
    if len(new_password) < 8:
        flash('新しいパスワードは8文字以上である必要があります。', 'danger')
        return redirect(url_for('admin_page'))

    hashed_password = generate_password_hash(new_password, method='pbkdf2:sha256')
    set_password_hash(hashed_password)

    log_activity('Password changed')
    flash('パスワードが正常に変更されました。', 'success')
    return redirect(url_for('admin_page'))

# --- API Endpoints (Mostly for admin) ---
@app.route('/api/reservations')
def get_reservations():
    return jsonify(reservations_db)

@app.route('/api/reservations', methods=['POST'])
def add_reservation():
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    date = data.get('date')
    start_time = data.get('start')
    end_time = data.get('end')
    customer_name = data.get('customer_name', '手動入力')

    if date not in reservations_db:
        reservations_db[date] = []

    reservations_db[date].append(data)

    log_reservation_judgment(
        'booking', date, f"{start_time}-{end_time}",
        customer_name, 1.0
    )
    log_activity(f"Manual reservation added: {customer_name} {date} {start_time}-{end_time}")

    return jsonify({'message': 'Reservation added'})

@app.route('/api/reservations/delete', methods=['POST'])
def delete_reservation_api():
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401
    data = request.json
    date = data.get('date')
    index = data.get('index')
    if date in reservations_db and 0 <= index < len(reservations_db[date]):
        removed = reservations_db[date].pop(index)
        log_activity(f"Reservation deleted: {removed}")
        return jsonify({'message': 'Reservation deleted'})
    return jsonify({'error': 'Invalid data'}), 400

@app.route('/api/process_email', methods=['POST'])
def process_email():
    # This endpoint now expects structured JSON from GAS
    data = request.json
    action_type = data.get('action_type') # 'booking' or 'cancellation'
    date = data.get('date')
    start_time = data.get('start_time')
    end_time = data.get('end_time') # Only for booking

    if not all([action_type, date, start_time]):
        return jsonify({'error': 'Missing data for email processing'}), 400

    if action_type == 'booking':
        if not end_time:
            return jsonify({'error': 'End time is required for booking'}), 400
        if date not in reservations_db:
            reservations_db[date] = []
        new_booking = {'type': 'gmail', 'start': start_time, 'end': end_time}
        reservations_db[date].append(new_booking)
        log_activity(f"GAS-processed booking added: {new_booking}")
        return jsonify({'message': f"予約を追加 (GAS): {date} {start_time} - {end_time}"}), 200

    elif action_type == 'cancellation':
        if date in reservations_db:
            initial_count = len(reservations_db[date])
            # Find and remove the first matching gmail type reservation
            found_and_removed = False
            for i, r in enumerate(reservations_db[date]):
                if r['start'] == start_time and r['type'] == 'gmail':
                    reservations_db[date].pop(i)
                    found_and_removed = True
                    break
            
            if found_and_removed:
                log_activity(f"GAS-processed cancellation: {date} {start_time}")
                return jsonify({'message': f"予約をキャンセル (GAS): {date} {start_time}"}), 200
            else:
                return jsonify({'error': '該当の予約が見つかりませんでした。'}), 404

    return jsonify({'error': '不明なアクションタイプです。'}), 400

# --- Gmail Sync Endpoints ---
@app.route('/api/gmail/debug', methods=['POST'])
def debug_gmail_credentials():
    """Gmail認証情報の詳細デバッグ（管理者のみ）"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    try:
        import json

        debug_info = {
            'vercel_env': bool(os.environ.get('VERCEL_ENV')),
            'has_credentials': bool(os.environ.get('GMAIL_CREDENTIALS_JSON')),
            'has_token': bool(os.environ.get('GMAIL_TOKEN_JSON')),
            'credentials_length': len(os.environ.get('GMAIL_CREDENTIALS_JSON', '')),
            'token_length': len(os.environ.get('GMAIL_TOKEN_JSON', ''))
        }

        # JSON妥当性チェック
        try:
            if os.environ.get('GMAIL_CREDENTIALS_JSON'):
                json.loads(os.environ.get('GMAIL_CREDENTIALS_JSON'))
                debug_info['credentials_json_valid'] = True
            else:
                debug_info['credentials_json_valid'] = False
        except:
            debug_info['credentials_json_valid'] = False

        try:
            if os.environ.get('GMAIL_TOKEN_JSON'):
                json.loads(os.environ.get('GMAIL_TOKEN_JSON'))
                debug_info['token_json_valid'] = True
            else:
                debug_info['token_json_valid'] = False
        except:
            debug_info['token_json_valid'] = False

        return jsonify(debug_info)
    except Exception as e:
        return jsonify({'error': f'Debug error: {str(e)}'}), 500

@app.route('/api/gas/webhook', methods=['POST'])
def gas_webhook():
    """Google Apps ScriptからのWebhook受信"""
    try:
        # 簡易認証チェック
        auth_header = request.headers.get('X-GAS-Secret')
        if auth_header != 'hallel_gas_2024':
            return jsonify({'error': 'Unauthorized'}), 401

        data = request.json
        if not data or 'reservations' not in data:
            return jsonify({'error': 'Invalid data format'}), 400

        reservations = data['reservations']
        added_count = 0
        cancelled_count = 0

        for reservation in reservations:
            date = reservation['date']
            if date not in reservations_db:
                reservations_db[date] = []

            # キャンセル処理
            if reservation.get('is_cancellation', False):
                removed = False
                for i, existing in enumerate(reservations_db[date]):
                    if (existing.get('start') == reservation['start'] and
                        existing.get('type') == reservation['type']):
                        reservations_db[date].pop(i)
                        removed = True
                        cancelled_count += 1
                        log_activity(f"GAS sync cancelled: {reservation['date']} {reservation['start']}-{reservation['end']} - {reservation.get('customer_name', 'N/A')}")
                        break
            else:
                # 重複チェック
                duplicate = False
                for existing in reservations_db[date]:
                    if (existing.get('start') == reservation['start'] and
                        existing.get('end') == reservation['end'] and
                        existing.get('customer_name') == reservation.get('customer_name')):
                        duplicate = True
                        break

                if not duplicate:
                    reservation_entry = {
                        'start': reservation['start'],
                        'end': reservation['end'],
                        'customer_name': reservation.get('customer_name', 'N/A'),
                        'type': 'gmail',
                        'source': 'gas'
                    }
                    reservations_db[date].append(reservation_entry)
                    added_count += 1
                    log_activity(f"GAS sync added: {reservation['date']} {reservation['start']}-{reservation['end']} - {reservation.get('customer_name', 'N/A')}")

        return jsonify({
            'success': True,
            'message': 'GAS sync completed',
            'added': added_count,
            'cancelled': cancelled_count,
            'total_found': len(reservations)
        }), 200

    except Exception as e:
        log_activity(f"GAS webhook error: {str(e)}")
        return jsonify({'error': 'Webhook processing failed'}), 500

@app.route('/api/gmail/sync', methods=['POST'])
def sync_gmail_reservations():
    """Gmailから予約情報を同期"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    if not GMAIL_ENABLED:
        return jsonify({'error': 'Gmail連携が有効になっていません'}), 503

    # Vercel環境での環境変数チェック
    if os.environ.get('VERCEL_ENV'):
        has_credentials = bool(os.environ.get('GMAIL_CREDENTIALS_JSON'))
        has_token = bool(os.environ.get('GMAIL_TOKEN_JSON'))

        if not has_credentials or not has_token:
            return jsonify({
                'error': 'Gmail認証情報が設定されていません。Vercelダッシュボードで環境変数を設定してください。',
                'missing': {
                    'credentials': not has_credentials,
                    'token': not has_token
                }
            }), 503

    try:
        # 高速Gmail同期を使用
        from gmail_fast_sync import FastGmailSync
        fast_sync = FastGmailSync()
        new_reservations = fast_sync.get_recent_reservations()

        added_count = 0
        cancelled_count = 0

        for reservation in new_reservations:
            date = reservation['date']
            start_time = reservation['start']
            end_time = reservation['end']
            customer_name = reservation.get('customer_name', 'N/A')
            action_type = reservation.get('action_type', 'booking')
            confidence = reservation.get('confidence', 1.0)

            if date not in reservations_db:
                reservations_db[date] = []

            # ログにメール判別結果を記録（予約システムへの追加は別途制御）
            log_reservation_judgment(
                action_type, date, f"{start_time}-{end_time}",
                customer_name, confidence
            )

            # キャンセルメールの場合は既存の予約を削除
            if action_type == 'cancellation':
                removed = False
                for i, existing in enumerate(reservations_db[date]):
                    if (existing.get('start') == start_time and
                        existing.get('customer_name') == customer_name):
                        reservations_db[date].pop(i)
                        removed = True
                        cancelled_count += 1
                        break

            # 予約メールの場合
            elif action_type == 'booking':
                # 重複チェック
                duplicate = False
                for existing in reservations_db[date]:
                    if (existing.get('start') == start_time and
                        existing.get('customer_name') == customer_name):
                        duplicate = True
                        break

                if not duplicate:
                    # 予約追加（7枠チェックはフロントエンド側で行う）
                    reservations_db[date].append({
                        'type': 'gmail',
                        'start': start_time,
                        'end': end_time,
                        'source': reservation['source'],
                        'sender': reservation.get('sender', 'N/A'),
                        'email_subject': reservation.get('email_subject', 'N/A'),
                        'message_id': reservation.get('message_id', 'N/A'),
                        'customer_name': customer_name,
                        'confidence': confidence,
                        'group': 1
                    })
                    added_count += 1

        summary_message = f'{added_count}件の予約を追加、{cancelled_count}件をキャンセルしました'
        return jsonify({
            'message': summary_message,
            'added': added_count,
            'cancelled': cancelled_count,
            'total_found': len(new_reservations),
            'details': f'検出されたメール: {len(new_reservations)}件 (追加: {added_count}, キャンセル: {cancelled_count})'
        }), 200

    except Exception as e:
        # セキュリティ: 詳細なエラー情報をログには記録するが、レスポンスには含めない
        error_detail = str(e)
        log_activity(f"Gmail sync error: {error_detail}")

        # 一般的なエラーメッセージのみをクライアントに返す
        if "authentication" in error_detail.lower() or "permission" in error_detail.lower():
            return jsonify({'error': 'Gmail認証に問題があります。管理者にお問い合わせください。'}), 500
        else:
            return jsonify({'error': 'Gmail同期中にエラーが発生しました。'}), 500

@app.route('/api/gmail/status')
def gmail_status():
    """Gmail連携の状態を確認"""
    # Vercel環境での認証情報チェック
    has_credentials = bool(os.environ.get('GMAIL_CREDENTIALS_JSON'))
    has_token = bool(os.environ.get('GMAIL_TOKEN_JSON'))

    if os.environ.get('VERCEL_ENV'):
        # Vercel環境
        gmail_ready = GMAIL_ENABLED and has_credentials and has_token
        status_msg = 'ready' if gmail_ready else 'missing_env_vars'
    else:
        # ローカル環境
        gmail_ready = GMAIL_ENABLED
        status_msg = 'ready' if gmail_ready else 'disabled'

    return jsonify({
        'enabled': GMAIL_ENABLED,
        'status': status_msg,
        'environment': 'vercel' if os.environ.get('VERCEL_ENV') else 'local',
        'has_credentials': has_credentials,
        'has_token': has_token
    })

# --- Hacomono Sync Endpoints ---
@app.route('/api/hacomono/sync', methods=['POST'])
def sync_hacomono_reservations():
    """hacomonoから予約情報を同期"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    if not HACOMONO_ENABLED:
        return jsonify({'error': 'hacomonoスクレイピングが有効になっていません'}), 503

    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        days_ahead = data.get('days', 7)  # デフォルト7日間
        store_name = data.get('store_name', '半蔵門店')  # デフォルト半蔵門店

        if not email or not password:
            return jsonify({'error': 'hacomonoのメール・パスワードが必要です'}), 400

        scraper = HacomonoScraper()
        start_date = datetime.now().strftime("%Y-%m-%d")
        end_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

        new_reservations = scraper.fetch_reservations_for_date_range(
            start_date, end_date, email, password, store_name
        )

        added_count = 0
        updated_count = 0

        for reservation in new_reservations:
            date = reservation['date']
            if date not in reservations_db:
                reservations_db[date] = []

            # 重複チェック（同じ時間の同じソースの予約を避ける）
            duplicate = False
            for existing in reservations_db[date]:
                if (existing.get('start') == reservation['start'] and
                    existing.get('source') == reservation['source']):
                    duplicate = True
                    break

            if not duplicate:
                reservations_db[date].append({
                    'type': reservation['type'],
                    'start': reservation['start'],
                    'end': reservation['end'],
                    'source': reservation['source'],
                    'customer_name': reservation.get('customer_name', 'N/A'),
                    'status': reservation.get('status', 'N/A'),
                    'group': len([r for r in reservations_db[date] if r.get('start') == reservation['start']]) + 1
                })
                added_count += 1
                log_activity(f"hacomono sync added: {reservation['date']} {reservation['start']}-{reservation['end']} ({reservation['type']}) - 顧客: {reservation.get('customer_name', 'N/A')}")
            else:
                updated_count += 1
                log_activity(f"hacomono sync skipped (duplicate): {reservation['date']} {reservation['start']}-{reservation['end']} ({reservation['type']})")

        summary_message = f'{added_count}件の予約を追加、{updated_count}件は重複スキップしました'
        return jsonify({
            'message': summary_message,
            'added': added_count,
            'skipped': updated_count,
            'total_found': len(new_reservations),
            'details': f'hacomonoから取得: {len(new_reservations)}件 (追加: {added_count}, スキップ: {updated_count})'
        }), 200

    except Exception as e:
        log_activity(f"hacomono sync error: {str(e)}")
        return jsonify({'error': f'hacomono同期エラー: {str(e)}'}), 500

@app.route('/api/hacomono/status')
def hacomono_status():
    """hacomono連携の状態を確認"""
    return jsonify({
        'enabled': HACOMONO_ENABLED,
        'status': 'ready' if HACOMONO_ENABLED else 'disabled'
    })

@app.route('/api/reservations/detailed')
def get_detailed_reservations():
    """予約の詳細情報を取得"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    detailed_reservations = []
    for date, reservations in reservations_db.items():
        for reservation in reservations:
            detailed_reservations.append({
                'date': date,
                'start': reservation.get('start'),
                'end': reservation.get('end'),
                'type': reservation.get('type'),
                'type_display': '貸切予約' if reservation.get('type') == 'charter' else '通常予約',
                'group': reservation.get('group', 1),
                'source': reservation.get('source', 'manual'),
                'source_display': 'Gmail自動' if reservation.get('source') == 'gmail_auto' else '手動入力',
                'sender': reservation.get('sender', 'N/A'),
                'email_subject': reservation.get('email_subject', 'N/A'),
                'message_id': reservation.get('message_id', 'N/A'),
                'customer_name': reservation.get('customer_name', 'N/A')
            })

    # 日付と時間順でソート
    detailed_reservations.sort(key=lambda x: (x['date'], x['start']))

    return jsonify({
        'reservations': detailed_reservations,
        'total_count': len(detailed_reservations)
    })

# --- Log Management API ---
@app.route('/api/logs')
def get_logs():
    """予約判別ログ一覧を取得"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    return jsonify({
        'logs': reservation_judgment_logs,
        'count': len(reservation_judgment_logs)
    })

@app.route('/api/logs', methods=['POST'])
def add_log():
    """手動予約判別ログエントリを追加"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    message = data.get('message', '').strip()

    if not message:
        return jsonify({'error': 'メッセージが空です'}), 400

    # 手動ログは特別フォーマット
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} 📝 MANUAL: {message} (管理者入力)"
    reservation_judgment_logs.append(log_entry)

    # Keep only last 200 reservation logs
    if len(reservation_judgment_logs) > 200:
        reservation_judgment_logs.pop(0)

    return jsonify({'message': 'ログが追加されました'})

@app.route('/api/logs/clear', methods=['POST'])
def clear_logs():
    """予約判別ログをクリア"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    global reservation_judgment_logs
    log_count = len(reservation_judgment_logs)
    reservation_judgment_logs.clear()

    # クリア操作もログに記録
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    clear_log = f"{timestamp} 🗑️ CLEAR: {log_count}件の予約判別ログをクリア (管理者操作)"
    reservation_judgment_logs.append(clear_log)

    return jsonify({
        'message': f'{log_count}件の予約判別ログをクリアしました',
        'cleared_count': log_count
    })

@app.route('/api/logs/export')
def export_logs():
    """予約判別ログをテキスト形式でエクスポート"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    log_text = '\n'.join(reservation_judgment_logs)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    response = app.response_class(
        response=log_text,
        status=200,
        mimetype='text/plain',
        headers={
            'Content-Disposition': f'attachment; filename=hallel_shibuya_reservation_judgment_logs_{timestamp}.txt'
        }
    )

    # エクスポート操作もログに記録
    export_timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    export_log = f"{export_timestamp} 📁 EXPORT: 予約判別ログをエクスポート (管理者操作)"
    reservation_judgment_logs.append(export_log)

    return response

# Vercel entry point - this is required for Vercel to work
app = app

# For local development
if __name__ == '__main__':
    app.run(debug=True, port=5002)

