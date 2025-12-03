# -*- coding: utf-8 -*-
"""
database.py - SQLite access layer for the posture analysis system.
Manages users, sessions, metrics, and reports.
"""

import json
import sqlite3

DB_PATH = "posture_system.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _ensure_column(cursor, table, column_name, column_def):
    cursor.execute(f"PRAGMA table_info({table});")
    existing = [row["name"] for row in cursor.fetchall()]
    if column_name not in existing:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_def};")


def initialize_database():
    conn = get_connection()
    try:
        cursor = conn.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                calibration_data TEXT,
                fps INTEGER,
                notes TEXT,
                image_path TEXT
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_duration_seconds REAL,
                standing_time_seconds REAL,
                sitting_time_seconds REAL,
                absence_time_seconds REAL,
                total_alerts INTEGER DEFAULT 0,
                bad_posture_percentage REAL DEFAULT 0,
                fps_average REAL,
                bag_file TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id INTEGER NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                pitch REAL,
                yaw REAL,
                roll REAL,
                elevation REAL,
                asymmetry REAL,
                shoulder_width REAL,
                standing INTEGER,
                score REAL,
                events TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id INTEGER NOT NULL,
                summary TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
            );
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS posture_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_id INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                frame_number INTEGER,
                
                -- Valores brutos (antes dos filtros)
                pitch_raw REAL,
                yaw_raw REAL,
                roll_raw REAL,
                trunk_pitch_raw REAL,
                trunk_roll_raw REAL,
                em_raw REAL,
                ed_raw REAL,
                
                -- Valores filtrados (após EMA/Median)
                pitch_filtered REAL,
                yaw_filtered REAL,
                roll_filtered REAL,
                trunk_pitch_filtered REAL,
                trunk_roll_filtered REAL,
                em_filtered REAL,
                ed_filtered REAL,
                
                -- Diferenças calculadas (angular_diff ou absoluta)
                pitch_diff REAL,
                yaw_diff REAL,
                roll_diff REAL,
                trunk_pitch_diff REAL,
                trunk_roll_diff REAL,
                
                -- Outros dados
                shoulder_width REAL,
                standing BOOLEAN DEFAULT 1,
                
                -- Eventos ativos
                pitch_on BOOLEAN DEFAULT 0,
                yaw_on BOOLEAN DEFAULT 0,
                roll_on BOOLEAN DEFAULT 0,
                trunk_pitch_on BOOLEAN DEFAULT 0,
                trunk_roll_on BOOLEAN DEFAULT 0,
                em_on BOOLEAN DEFAULT 0,
                ed_on BOOLEAN DEFAULT 0,
                head_extension_on BOOLEAN DEFAULT 0,
                
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
                FOREIGN KEY (session_id) REFERENCES sessions (id) ON DELETE CASCADE
            );
            """
        )

        # Criar índices para consultas rápidas
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_posture_readings_user 
            ON posture_readings(user_id);
            """
        )
        
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_posture_readings_session 
            ON posture_readings(session_id);
            """
        )
        
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_posture_readings_timestamp 
            ON posture_readings(timestamp);
            """
        )

        _ensure_column(cursor, "users", "calibration_data", "TEXT")
        _ensure_column(cursor, "users", "fps", "INTEGER")
        _ensure_column(cursor, "users", "notes", "TEXT")
        _ensure_column(cursor, "users", "updated_at", "DATETIME DEFAULT CURRENT_TIMESTAMP")
        _ensure_column(cursor, "sessions", "standing_time_seconds", "REAL")
        _ensure_column(cursor, "sessions", "sitting_time_seconds", "REAL")
        _ensure_column(cursor, "sessions", "absence_time_seconds", "REAL")
        _ensure_column(cursor, "sessions", "fps_average", "REAL")
        _ensure_column(cursor, "sessions", "bag_file", "TEXT")

        conn.commit()
    finally:
        conn.close()


def _get_numeric(mapping, keys, cast=float):
    if mapping is None:
        return None
    for key in keys:
        if key in mapping and mapping[key] is not None:
            try:
                return cast(mapping[key])
            except (TypeError, ValueError):
                continue
    return None


def create_user(username, calibration=None, image_path=None):
    calibration = calibration or {}
    calibration_json = json.dumps(calibration)
    fps = calibration.get("fps")
    notes = calibration.get("notes")

    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO users (username, calibration_data, fps, notes, image_path, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(username) DO UPDATE SET
                calibration_data = excluded.calibration_data,
                fps = excluded.fps,
                notes = excluded.notes,
                image_path = excluded.image_path,
                updated_at = CURRENT_TIMESTAMP
            """,
            (username, calibration_json, fps, notes, image_path),
        )
        conn.commit()
        return True
    except Exception as exc:
        print(f"[DB] Failed to create or update user {username}: {exc}")
        return False
    finally:
        conn.close()


def get_user(username):
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        if not row:
            return None
        data = dict(row)
        calibration_json = data.get("calibration_data")
        data["calibration_data"] = json.loads(calibration_json) if calibration_json else None
        return data
    finally:
        conn.close()


def get_user_calibration(username):
    user = get_user(username)
    return user.get("calibration_data") if user else None


def list_users():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT username FROM users ORDER BY username").fetchall()
        return [row["username"] for row in rows]
    finally:
        conn.close()


def delete_user(username):
    conn = get_connection()
    try:
        result = conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        return result.rowcount > 0
    except Exception as exc:
        print(f"[DB] Failed to delete user {username}: {exc}")
        return False
    finally:
        conn.close()


def create_session(user_id, summary=None):
    summary = summary or {}
    duration = _get_numeric(summary, ("session_duration_seconds", "session_duration"), float)
    standing_time = _get_numeric(summary, ("standing_time_seconds", "standing_time"), float)
    sitting_time = _get_numeric(summary, ("sitting_time_seconds", "sitting_time"), float)
    absence_time = _get_numeric(summary, ("absence_time_seconds", "absence_time"), float)
    total_alerts = _get_numeric(summary, ("total_alerts",), int) or 0
    bad_posture_pct = _get_numeric(summary, ("bad_posture_percentage",), float)
    fps_average = _get_numeric(summary, ("fps_average",), float)
    bag_file = summary.get("bag_file")

    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO sessions (
                user_id,
                session_duration_seconds,
                standing_time_seconds,
                sitting_time_seconds,
                absence_time_seconds,
                total_alerts,
                bad_posture_percentage,
                fps_average,
                bag_file
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                duration,
                standing_time,
                sitting_time,
                absence_time,
                total_alerts,
                bad_posture_pct,
                fps_average,
                bag_file,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_sessions(user_id):
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM sessions
            WHERE user_id = ?
            ORDER BY timestamp DESC, id DESC
            """,
            (user_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_sessions_by_month(user_id, year, month):
    conn = get_connection()
    try:
        ym = f"{year}-{int(month):02d}"
        rows = conn.execute(
            """
            SELECT * FROM sessions
            WHERE user_id = ? AND strftime('%Y-%m', timestamp) = ?
            ORDER BY timestamp DESC, id DESC
            """,
            (user_id, ym),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_latest_session(user_id):
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM sessions
            WHERE user_id = ?
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def insert_metric(session_id, data):
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO metrics (
                session_id,
                pitch,
                yaw,
                roll,
                elevation,
                asymmetry,
                shoulder_width,
                standing,
                score,
                events
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                data.get("pitch"),
                data.get("yaw"),
                data.get("roll"),
                data.get("elevation"),
                data.get("asymmetry"),
                data.get("shoulder_width"),
                int(data.get("standing", 1)),
                data.get("score"),
                json.dumps(data.get("events")),
            ),
        )
        conn.commit()
    except Exception as exc:
        print(f"[DB] Failed to insert metrics: {exc}")
    finally:
        conn.close()


def insert_report(user_id, session_id, summary):
    conn = get_connection()
    try:
        conn.execute(
            """
            INSERT INTO reports (user_id, session_id, summary)
            VALUES (?, ?, ?)
            """,
            (user_id, session_id, json.dumps(summary)),
        )
        conn.commit()
    finally:
        conn.close()


def _parse_report_row(row):
    data = dict(row)
    summary = data.get("summary")
    data["summary"] = json.loads(summary) if summary else {}
    return data


def get_reports(user_id=None):
    conn = get_connection()
    try:
        if user_id is not None:
            rows = conn.execute(
                """
                SELECT
                    r.id,
                    r.user_id,
                    u.username,
                    r.session_id,
                    r.summary,
                    r.created_at
                FROM reports r
                JOIN users u ON u.id = r.user_id
                WHERE r.user_id = ?
                ORDER BY r.created_at ASC, r.id ASC
                """,
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    r.id,
                    r.user_id,
                    u.username,
                    r.session_id,
                    r.summary,
                    r.created_at
                FROM reports r
                JOIN users u ON u.id = r.user_id
                ORDER BY r.created_at ASC, r.id ASC
                """
            ).fetchall()
        return [_parse_report_row(row) for row in rows]
    finally:
        conn.close()


def get_reports_for_username(username):
    user_id = get_user_id(username)
    if user_id is None:
        return []
    return get_reports(user_id=user_id)


def get_latest_report(username):
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT
                r.id,
                r.user_id,
                u.username,
                r.session_id,
                r.summary,
                r.created_at
            FROM reports r
            JOIN users u ON u.id = r.user_id
            WHERE u.username = ?
            ORDER BY r.created_at DESC, r.id DESC
            LIMIT 1
            """,
            (username,),
        ).fetchone()
        return _parse_report_row(row) if row else None
    finally:
        conn.close()


def get_user_id(username):
    conn = get_connection()
    try:
        row = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


# --------- Funções para Posture Readings ---------

def insert_posture_readings_batch(readings_list):
    """
    Insere múltiplas leituras de postura em lote (batch insert).
    
    Args:
        readings_list: Lista de dicts, cada um contendo os dados de uma leitura
    
    Returns:
        True se sucesso, False caso contrário
    """
    if not readings_list:
        return True
    
    conn = get_connection()
    try:
        cursor = conn.cursor()
        
        for reading in readings_list:
            cursor.execute(
                """
                INSERT INTO posture_readings (
                    user_id, session_id, timestamp, frame_number,
                    pitch_raw, yaw_raw, roll_raw, trunk_pitch_raw, trunk_roll_raw, em_raw, ed_raw,
                    pitch_filtered, yaw_filtered, roll_filtered, trunk_pitch_filtered, trunk_roll_filtered, em_filtered, ed_filtered,
                    pitch_diff, yaw_diff, roll_diff, trunk_pitch_diff, trunk_roll_diff,
                    shoulder_width, standing,
                    pitch_on, yaw_on, roll_on, trunk_pitch_on, trunk_roll_on, em_on, ed_on, head_extension_on
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    reading.get('user_id'),
                    reading.get('session_id'),
                    reading.get('timestamp'),
                    reading.get('frame_number'),
                    # Brutos
                    reading.get('pitch_raw'),
                    reading.get('yaw_raw'),
                    reading.get('roll_raw'),
                    reading.get('trunk_pitch_raw'),
                    reading.get('trunk_roll_raw'),
                    reading.get('em_raw'),
                    reading.get('ed_raw'),
                    # Filtrados
                    reading.get('pitch_filtered'),
                    reading.get('yaw_filtered'),
                    reading.get('roll_filtered'),
                    reading.get('trunk_pitch_filtered'),
                    reading.get('trunk_roll_filtered'),
                    reading.get('em_filtered'),
                    reading.get('ed_filtered'),
                    # Diferenças
                    reading.get('pitch_diff'),
                    reading.get('yaw_diff'),
                    reading.get('roll_diff'),
                    reading.get('trunk_pitch_diff'),
                    reading.get('trunk_roll_diff'),
                    # Outros
                    reading.get('shoulder_width'),
                    1,  # standing (sempre True quando salva)
                    # Eventos
                    int(reading.get('pitch_on', False)),
                    int(reading.get('yaw_on', False)),
                    int(reading.get('roll_on', False)),
                    int(reading.get('trunk_pitch_on', False)),
                    int(reading.get('trunk_roll_on', False)),
                    int(reading.get('em_on', False)),
                    int(reading.get('ed_on', False)),
                    int(reading.get('head_extension_on', False)),
                ),
            )
        
        conn.commit()
        return True
    except Exception as exc:
        print(f"[DB] Failed to insert posture readings batch: {exc}")
        return False
    finally:
        conn.close()


def get_posture_readings(user_id=None, session_id=None, start_time=None, end_time=None, limit=None):
    """
    Consulta leituras de postura com filtros opcionais.
    
    Args:
        user_id: Filtrar por usuário
        session_id: Filtrar por sessão
        start_time: Timestamp inicial
        end_time: Timestamp final
        limit: Número máximo de registros
    
    Returns:
        Lista de dicts com as leituras
    """
    conn = get_connection()
    try:
        query = "SELECT * FROM posture_readings WHERE 1=1"
        params = []
        
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        
        if start_time is not None:
            query += " AND timestamp >= ?"
            params.append(start_time)
        
        if end_time is not None:
            query += " AND timestamp <= ?"
            params.append(end_time)
        
        query += " ORDER BY timestamp ASC"
        
        if limit is not None:
            query += f" LIMIT {int(limit)}"
        
        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_posture_readings_stats(user_id=None, session_id=None):
    """
    Calcula estatísticas agregadas das leituras de postura.
    
    Args:
        user_id: Filtrar por usuário
        session_id: Filtrar por sessão
    
    Returns:
        Dict com estatísticas (média, min, max) de cada métrica
    """
    conn = get_connection()
    try:
        query = """
            SELECT 
                COUNT(*) as total_readings,
                AVG(pitch_diff) as pitch_diff_mean,
                MIN(pitch_diff) as pitch_diff_min,
                MAX(pitch_diff) as pitch_diff_max,
                AVG(yaw_diff) as yaw_diff_mean,
                MIN(yaw_diff) as yaw_diff_min,
                MAX(yaw_diff) as yaw_diff_max,
                AVG(roll_diff) as roll_diff_mean,
                MIN(roll_diff) as roll_diff_min,
                MAX(roll_diff) as roll_diff_max,
                AVG(trunk_pitch_diff) as trunk_pitch_diff_mean,
                MIN(trunk_pitch_diff) as trunk_pitch_diff_min,
                MAX(trunk_pitch_diff) as trunk_pitch_diff_max,
                AVG(trunk_roll_diff) as trunk_roll_diff_mean,
                MIN(trunk_roll_diff) as trunk_roll_diff_min,
                MAX(trunk_roll_diff) as trunk_roll_diff_max,
                AVG(em_filtered) as em_mean,
                MIN(em_filtered) as em_min,
                MAX(em_filtered) as em_max,
                AVG(ed_filtered) as ed_mean,
                MIN(ed_filtered) as ed_min,
                MAX(ed_filtered) as ed_max,
                SUM(pitch_on) as pitch_on_count,
                SUM(yaw_on) as yaw_on_count,
                SUM(roll_on) as roll_on_count,
                SUM(trunk_pitch_on) as trunk_pitch_on_count,
                SUM(trunk_roll_on) as trunk_roll_on_count,
                SUM(em_on) as em_on_count,
                SUM(ed_on) as ed_on_count,
                SUM(head_extension_on) as head_extension_on_count
            FROM posture_readings
            WHERE 1=1
        """
        params = []
        
        if user_id is not None:
            query += " AND user_id = ?"
            params.append(user_id)
        
        if session_id is not None:
            query += " AND session_id = ?"
            params.append(session_id)
        
        row = conn.execute(query, params).fetchone()
        return dict(row) if row else {}
    finally:
        conn.close()


if __name__ == "__main__":
    initialize_database()
    print("Banco de dados inicializado com sucesso.")
