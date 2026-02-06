from flask import Flask, render_template, jsonify, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
import re
import os
from datetime import datetime, timedelta
import logging

# Disable features that require file access or external dependencies in Vercel
GMAIL_ENABLED = False
HACOMONO_ENABLED = False

# --- App Initialization ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'hanzomon-fallback-secret-key-for-vercel')

# --- In-memory storage for Vercel (no file system access) ---
# Default admin password hash for 'hanzomon0000admin'
DEFAULT_PASSWORD_HASH = 'pbkdf2:sha256:260000$rKzGZQZ6$2a3f5b1c8d9e0f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e'
current_password_hash = generate_password_hash('hanzomon0000admin', method='pbkdf2:sha256')

# Simple in-memory logging for Vercel
activity_logs = []

def log_activity(action):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_entry = f"{timestamp} - Action: {action}"
    activity_logs.append(log_entry)
    # Keep only last 100 logs to prevent memory issues
    if len(activity_logs) > 100:
        activity_logs.pop(0)

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
    return session.get('logged_in', False)

@app.route('/admin')
def admin_page():
    if not is_logged_in():
        return redirect(url_for('login'))

    # Use in-memory logs instead of file-based logs
    logs = activity_logs.copy()
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
    if date not in reservations_db:
        reservations_db[date] = []
    reservations_db[date].append(data)
    log_activity(f"Manual reservation added: {data}")
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
@app.route('/api/gmail/sync', methods=['POST'])
def sync_gmail_reservations():
    """Gmailから予約情報を同期"""
    if not is_logged_in():
        return jsonify({'error': 'Unauthorized'}), 401

    if not GMAIL_ENABLED:
        return jsonify({'error': 'Gmail連携が有効になっていません'}), 503

    try:
        parser = GmailReservationParser()
        new_reservations = parser.fetch_and_parse_reservations()

        added_count = 0
        cancelled_count = 0

        for reservation in new_reservations:
            date = reservation['date']
            if date not in reservations_db:
                reservations_db[date] = []

            # キャンセルメールの場合は既存の予約を削除
            if reservation.get('is_cancellation', False):
                removed = False
                for i, existing in enumerate(reservations_db[date]):
                    if (existing.get('start') == reservation['start'] and
                        existing.get('type') == reservation['type']):
                        reservations_db[date].pop(i)
                        removed = True
                        cancelled_count += 1
                        log_activity(f"Gmail sync cancelled: {reservation['date']} {reservation['start']}-{reservation['end']} ({reservation['type']}) - 顧客名: {reservation.get('customer_name', 'N/A')} - 件名: {reservation.get('email_subject', 'N/A')}")
                        break

                if not removed:
                    log_activity(f"Gmail sync cancellation failed (not found): {reservation['date']} {reservation['start']}-{reservation['end']} ({reservation['type']}) - 件名: {reservation.get('email_subject', 'N/A')}")

            # 通常の予約追加処理
            else:
                # 重複チェック（同じ時間の同じタイプの予約を避ける）
                duplicate = False
                for existing in reservations_db[date]:
                    if (existing.get('start') == reservation['start'] and
                        existing.get('type') == reservation['type']):
                        duplicate = True
                        break

                if not duplicate:
                    reservations_db[date].append({
                        'type': reservation['type'],
                        'start': reservation['start'],
                        'end': reservation['end'],
                        'source': reservation['source'],
                        'sender': reservation.get('sender', 'N/A'),
                        'email_subject': reservation.get('email_subject', 'N/A'),
                        'message_id': reservation.get('message_id', 'N/A'),
                        'customer_name': reservation.get('customer_name', 'N/A'),
                        'group': len([r for r in reservations_db[date] if r.get('start') == reservation['start']]) + 1
                    })
                    added_count += 1
                    log_activity(f"Gmail sync added: {reservation['date']} {reservation['start']}-{reservation['end']} ({reservation['type']}) - 顧客名: {reservation.get('customer_name', 'N/A')} - 件名: {reservation.get('email_subject', 'N/A')}")
                else:
                    log_activity(f"Gmail sync skipped (duplicate): {reservation['date']} {reservation['start']}-{reservation['end']} ({reservation['type']}) - 件名: {reservation.get('email_subject', 'N/A')}")

        summary_message = f'{added_count}件の予約を追加、{cancelled_count}件をキャンセルしました'
        return jsonify({
            'message': summary_message,
            'added': added_count,
            'cancelled': cancelled_count,
            'total_found': len(new_reservations),
            'details': f'検出されたメール: {len(new_reservations)}件 (追加: {added_count}, キャンセル: {cancelled_count})'
        }), 200

    except Exception as e:
        log_activity(f"Gmail sync error: {str(e)}")
        return jsonify({'error': f'Gmail同期エラー: {str(e)}'}), 500

@app.route('/api/gmail/status')
def gmail_status():
    """Gmail連携の状態を確認"""
    return jsonify({
        'enabled': GMAIL_ENABLED,
        'status': 'ready' if GMAIL_ENABLED else 'disabled'
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

# Vercel entry point - this is required for Vercel to work
app = app

# For local development
if __name__ == '__main__':
    app.run(debug=True, port=5002)

