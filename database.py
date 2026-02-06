import sqlite3
import json
from datetime import datetime
import os

class ReservationDB:
    def __init__(self, db_name='hanzomon_reservations.db'):
        self.db_name = db_name
        self.init_database()

    def init_database(self):
        """データベースとテーブルを初期化"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                reservation_type TEXT NOT NULL,
                group_number INTEGER DEFAULT 1,
                source TEXT DEFAULT 'manual',
                email_subject TEXT,
                message_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # インデックスを作成
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_date ON reservations(date)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_start_time ON reservations(start_time)')

        conn.commit()
        conn.close()

    def add_reservation(self, date, start_time, end_time, reservation_type, group_number=1, source='manual', email_subject=None, message_id=None):
        """予約を追加"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO reservations (date, start_time, end_time, reservation_type, group_number, source, email_subject, message_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date, start_time, end_time, reservation_type, group_number, source, email_subject, message_id))

        reservation_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return reservation_id

    def get_reservations_by_date(self, date):
        """指定日の予約を取得"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT id, start_time, end_time, reservation_type, group_number, source, email_subject, message_id
            FROM reservations
            WHERE date = ?
            ORDER BY start_time
        ''', (date,))

        rows = cursor.fetchall()
        conn.close()

        reservations = []
        for row in rows:
            reservations.append({
                'id': row[0],
                'start': row[1],
                'end': row[2],
                'type': row[3],
                'group': row[4],
                'source': row[5],
                'email_subject': row[6],
                'message_id': row[7]
            })

        return reservations

    def get_all_reservations(self):
        """全ての予約をdict形式で取得（既存のAPIとの互換性のため）"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute('''
            SELECT date, start_time, end_time, reservation_type, group_number, source, email_subject, message_id
            FROM reservations
            ORDER BY date, start_time
        ''')

        rows = cursor.fetchall()
        conn.close()

        reservations_dict = {}
        for row in rows:
            date = row[0]
            if date not in reservations_dict:
                reservations_dict[date] = []

            reservations_dict[date].append({
                'start': row[1],
                'end': row[2],
                'type': row[3],
                'group': row[4],
                'source': row[5],
                'email_subject': row[6],
                'message_id': row[7]
            })

        return reservations_dict

    def delete_reservation(self, reservation_id):
        """予約を削除"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute('DELETE FROM reservations WHERE id = ?', (reservation_id,))
        deleted_count = cursor.rowcount

        conn.commit()
        conn.close()
        return deleted_count > 0

    def delete_reservation_by_details(self, date, start_time, reservation_type):
        """日付・時間・タイプで予約を削除"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        cursor.execute('''
            DELETE FROM reservations
            WHERE date = ? AND start_time = ? AND reservation_type = ?
            LIMIT 1
        ''', (date, start_time, reservation_type))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()
        return deleted_count > 0

    def reservation_exists(self, date, start_time, reservation_type, message_id=None):
        """重複チェック"""
        conn = sqlite3.connect(self.db_name)
        cursor = conn.cursor()

        if message_id:
            cursor.execute('''
                SELECT COUNT(*) FROM reservations
                WHERE (date = ? AND start_time = ? AND reservation_type = ?) OR message_id = ?
            ''', (date, start_time, reservation_type, message_id))
        else:
            cursor.execute('''
                SELECT COUNT(*) FROM reservations
                WHERE date = ? AND start_time = ? AND reservation_type = ?
            ''', (date, start_time, reservation_type))

        count = cursor.fetchone()[0]
        conn.close()
        return count > 0

    def migrate_from_memory(self, memory_db):
        """メモリ内のデータをSQLiteに移行"""
        migrated_count = 0
        for date, reservations in memory_db.items():
            for reservation in reservations:
                if not self.reservation_exists(date, reservation['start'], reservation['type']):
                    self.add_reservation(
                        date=date,
                        start_time=reservation['start'],
                        end_time=reservation['end'],
                        reservation_type=reservation['type'],
                        group_number=reservation.get('group', 1),
                        source=reservation.get('source', 'manual')
                    )
                    migrated_count += 1
        return migrated_count

    def backup_to_json(self, backup_file=None):
        """JSONファイルにバックアップ"""
        if not backup_file:
            backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        reservations = self.get_all_reservations()
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(reservations, f, ensure_ascii=False, indent=2)

        return backup_file

    def restore_from_json(self, backup_file):
        """JSONファイルから復元"""
        with open(backup_file, 'r', encoding='utf-8') as f:
            reservations_data = json.load(f)

        restored_count = self.migrate_from_memory(reservations_data)
        return restored_count