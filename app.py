# -*- coding: utf-8 -*-
"""
AplicaÃ§Ã£o Flask - API REST e WebSocket
Interface web para análise de postura em tempo real
"""

import os
import logging
from flask import Flask, render_template, jsonify, Response
from flask_socketio import SocketIO, emit
import time

from posture_analyzer import PostureAnalyzer, check_camera_connection
import database

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

database.initialize_database()

# --------- Flask App ---------
app = Flask(__name__)
app.config['SECRET_KEY'] = 'posture_analyzer_secret'
socketio = SocketIO(app, cors_allowed_origins="*")

# Instância global do analisador
analyzer = PostureAnalyzer()

# Estado global da câmara
camera_connected = False

def update_camera_status():
    """Atualiza o status da câmara e notifica clientes via WebSocket"""
    global camera_connected
    new_status = check_camera_connection()
    
    if new_status != camera_connected:
        camera_connected = new_status
        logger.info(f"Status da câmara alterado: {'Conectada' if camera_connected else 'Desconectada'}")
        socketio.emit('camera_status', {
            'connected': camera_connected,
            'message': 'câmara RealSense conectada' if camera_connected else 'câmara RealSense não detetada'
        })
    
    return camera_connected

def camera_monitor_loop():
    """Loop de monitoramento da câmara em background"""
    while True:
        update_camera_status()
        time.sleep(5)

# --------- Rotas HTTP ---------
@app.route('/')
def index():
    return render_template('main.html')

@app.route('/api/camera/status')
def get_camera_status():
    """Endpoint REST para verificar status da câmara"""
    is_connected = check_camera_connection()
    return jsonify({
        'connected': is_connected,
        'message': 'câmara RealSense conectada' if is_connected else 'câmara RealSense não detetada'
    })

# Rotas para páginas específicas (compatibilidade)
@app.route('/criar-usuario')
def criar_usuario():
    return render_template('main.html')

@app.route('/iniciar-analise')
def iniciar_analise():
    return render_template('main.html')

@app.route('/apagar-usuario')
def apagar_usuario():
    return render_template('main.html')

@app.route('/verificar-leituras')
def verificar_leituras():
    return render_template('main.html')

@app.route('/video_feed')
def video_feed():
    """Endpoint de streaming de vÃ­deo"""
    return Response(analyzer.generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/api/users')
def get_users():
    """Endpoint para obter lista de usuários"""
    users = database.list_users()
    return jsonify({'users': users})

@app.route('/api/user/<username>', methods=['DELETE'])
def delete_user(username):
    """Endpoint para apagar um usuario"""
    try:
        if not database.delete_user(username):
            return jsonify({'error': f"Usuario {username} nao encontrado"}), 404

        if analyzer.current_user == username:
            analyzer.stop_analysis()

        logger.info(f"Usuario '{username}' removido do banco de dados.")
        return jsonify({'message': f"Usuario {username} apagado com sucesso."})

    except Exception as e:
        logger.error(f"Erro ao apagar usuario '{username}': {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/<username>')
def get_user_reports(username):
    """Endpoint para obter relatorios de um usuario especifico"""
    try:
        rows = database.get_reports_for_username(username)
        if not rows:
            return jsonify({'error': f'Nenhum relatorio encontrado para o usuario {username}'}), 404

        reports = []
        for row in rows:
            summary = dict(row['summary']) if isinstance(row.get('summary'), dict) else {}
            summary.setdefault('user', row.get('username', username))
            summary.setdefault('session_id', row.get('session_id'))
            summary.setdefault('created_at', row.get('created_at'))
            reports.append(summary)

        return jsonify({'reports': reports, 'total': len(reports)})
    except Exception as e:
        logger.error(f"Erro ao obter relatorios para {username}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports')
def get_all_reports():
    """Endpoint para obter todos os relatorios disponiveis"""
    try:
        rows = database.get_reports()
        if not rows:
            return jsonify({'reports': [], 'users': []})

        reports = []
        users_with_reports = set()

        for row in rows:
            summary = dict(row['summary']) if isinstance(row.get('summary'), dict) else {}
            username = row.get('username')
            if username:
                summary.setdefault('user', username)
                users_with_reports.add(username)
            summary.setdefault('session_id', row.get('session_id'))
            summary.setdefault('created_at', row.get('created_at'))
            reports.append(summary)

        reports.sort(key=lambda item: item.get('created_at') or '', reverse=True)

        return jsonify({
            'reports': reports,
            'total': len(reports),
            'users_with_reports': sorted(users_with_reports)
        })

    except Exception as e:
        logger.error(f"Erro ao obter relatorios: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/<username>/latest')
def get_user_latest_report(username):
    """Endpoint para obter o relatorio mais recente de um usuario"""
    try:
        row = database.get_latest_report(username)
        if not row:
            return jsonify({'error': f'Nenhum relatorio encontrado para o usuario {username}'}), 404

        summary = dict(row['summary']) if isinstance(row.get('summary'), dict) else {}
        summary.setdefault('user', row.get('username', username))
        summary.setdefault('session_id', row.get('session_id'))
        summary.setdefault('created_at', row.get('created_at'))

        return jsonify({'report': summary})
    except Exception as e:
        logger.error(f"Erro ao obter ultimo relatorio de {username}: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/reports/summary')
def get_reports_summary():
    """Endpoint para obter resumo de todos os relatorios"""
    try:
        rows = database.get_reports()
        if not rows:
            return jsonify({'summary': {}, 'users_with_reports': [], 'total_users': 0})

        summary = {}
        users_with_reports = set()

        for row in rows:
            username = row.get('username')
            if not username:
                continue

            users_with_reports.add(username)
            data = row.get('summary') if isinstance(row.get('summary'), dict) else {}

            user_stats = summary.setdefault(username, {
                'total_sessions': 0,
                'total_duration_seconds': 0.0,
                'total_alerts': 0,
                'bad_posture_sum': 0.0,
                'latest_session': data.get('timestamp') or row.get('created_at')
            })

            user_stats['total_sessions'] += 1
            user_stats['total_duration_seconds'] += float(data.get('session_duration_seconds', 0) or 0)
            user_stats['total_alerts'] += int(data.get('total_alerts', 0) or 0)
            user_stats['bad_posture_sum'] += float(data.get('bad_posture_percentage', 0) or 0)
            if data.get('timestamp'):
                user_stats['latest_session'] = data.get('timestamp')
            elif row.get('created_at'):
                user_stats['latest_session'] = row.get('created_at')

        summary_payload = {}
        for username, stats in summary.items():
            sessions = stats['total_sessions']
            avg_bad_posture = (stats['bad_posture_sum'] / sessions) if sessions else 0.0
            summary_payload[username] = {
                'total_sessions': sessions,
                'total_duration_hours': round(stats['total_duration_seconds'] / 3600, 2),
                'total_alerts': stats['total_alerts'],
                'avg_bad_posture_percentage': round(avg_bad_posture, 1),
                'latest_session': stats.get('latest_session', 'N/A')
            }

        return jsonify({
            'summary': summary_payload,
            'users_with_reports': sorted(users_with_reports),
            'total_users': len(users_with_reports)
        })

    except Exception as e:
        logger.error(f"Erro ao obter resumo dos relatorios: {e}")
        return jsonify({'error': str(e)}), 500
@socketio.on('connect')
def handle_connect():
    logger.info('Cliente conectado')
    emit('connected', {'message': 'Conectado ao servidor de análise de postura'})
    is_connected = check_camera_connection()
    emit('camera_status', {
        'connected': is_connected,
        'message': 'câmara RealSense conectada' if is_connected else 'câmara RealSense não detetada'
    })

@socketio.on('check_camera')
def handle_check_camera():
    """Handler para verificação manual do status da câmara"""
    is_connected = check_camera_connection()
    emit('camera_status', {
        'connected': is_connected,
        'message': 'câmara RealSense conectada' if is_connected else 'câmara RealSense não detetada'
    })

@socketio.on('disconnect')
def handle_disconnect():
    logger.info('Cliente desconectado')

@socketio.on('start_analysis')
def handle_start_analysis(data):
    user = data.get('user')
    if not user:
        emit('error', {'message': 'usuário não especificado'})
        return
    
    if not check_camera_connection():
        emit('error', {'message': 'câmara RealSense não detetada. Conecte a câmara e tente novamente.'})
        return
    
    success = analyzer.start_analysis(user, socketio)
    if success:
        emit('analysis_started', {'user': user})
    else:
        emit('error', {'message': f'Erro ao iniciar análise para usuário {user}'})

@socketio.on('stop_analysis')
def handle_stop_analysis():
    analyzer.stop_analysis()
    emit('analysis_stopped')

@socketio.on('start_calibration')
def handle_start_calibration(data):
    user = data.get('user')
    if not user:
        emit('error', {'message': 'Nome de usuário não especificado'})
        return
    
    if not check_camera_connection():
        emit('error', {'message': 'câmara RealSense não detetada. Conecte a câmara e tente novamente.'})
        return
    
    success = analyzer.start_calibration(user, socketio)
    if success:
        emit('calibration_started', {'user': user})
    else:
        emit('error', {'message': f'Erro ao iniciar calibração para usuário {user}'})

@socketio.on('stop_calibration')
def handle_stop_calibration():
    analyzer.stop_calibration()
    emit('calibration_stopped')

@socketio.on('start_calibration_collection')
def handle_start_calibration_collection():
    if analyzer.calibrating and analyzer.calibration_data:
        analyzer.calibration_data['started'] = True
        emit('calibration_collection_started')
    else:
        emit('error', {'message': 'calibração não está ativa'})

@socketio.on('save_calibration')
def handle_save_calibration():
    success = analyzer.save_calibration()
    if success:
        emit('calibration_saved', {'message': 'calibração salva com sucesso!'})
    else:
        emit('error', {'message': 'Erro ao salvar calibração'})

# --- SESSÕES DO USUÁRIO (para popular o segundo dropdown) ---
@app.route('/api/sessions/<username>')
def api_sessions_for_user(username):
    """Lista as sessões (id + timestamp) de um usuário, mais recentes primeiro"""
    try:
        user_id = database.get_user_id(username)
        if not user_id:
            return jsonify([])

        sessions = database.get_sessions(user_id)  # já ordena por timestamp DESC
        # garante campos id e timestamp (pode haver None se sessão antiga não tiver timestamp)
        payload = [{"id": s["id"], "timestamp": s.get("timestamp")} for s in sessions]
        return jsonify(payload)
    except Exception as e:
        logger.error(f"Erro ao listar sessões de {username}: {e}")
        return jsonify({"error": str(e)}), 500


# --- RELATÓRIO POR SESSÃO (para carregar a sessão escolhida) ---
@app.route('/api/reports/<username>/<int:session_id>')
def api_report_for_session(username, session_id):
    """Retorna o summary do relatório da sessão escolhida"""
    try:
        user_id = database.get_user_id(username)
        if not user_id:
            return jsonify({"error": "Usuário não encontrado"}), 404

        conn = database.get_connection()
        try:
            row = conn.execute(
                """
                SELECT summary, created_at
                FROM reports
                WHERE user_id = ? AND session_id = ?
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (user_id, session_id),
            ).fetchone()
        finally:
            conn.close()

        if not row:
            return jsonify({"error": "Relatório não encontrado"}), 404

        return jsonify({
            "summary": (row["summary"] and __import__("json").loads(row["summary"])) or {},
            "created_at": row["created_at"]
        })
    except Exception as e:
        logger.error(f"Erro ao obter relatório de {username} (sessão {session_id}): {e}")
        return jsonify({"error": str(e)}), 500


# --------- InicializaÃ§Ã£o ---------
if __name__ == '__main__':
    try:
        logger.info("Iniciando servidor de análise de postura...")
        logger.info("Acesse http://localhost:5000 para ver o dashboard")
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    except KeyboardInterrupt:
        logger.info("Parando servidor...")
        analyzer.stop_analysis()











