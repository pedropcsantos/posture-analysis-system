# -*- coding: utf-8 -*-
"""
Má³dulo de análise de Postura
Gerencia câmara RealSense, calibração e análise em tempo real
"""

import time
import os
import numpy as np
import cv2
import mediapipe as mp
import pyrealsense2 as rs
import logging
import json 

from posture_detector import PostureDetector, Latch, angular_diff
import database

logger = logging.getLogger(__name__)

def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# --------- Funções Utilitárias ---------
def load_user_row(user, prefer_last=True):
    """Carrega dados de calibraçáo de um usuário armazenados no banco de dados."""
    del prefer_last  # compatibilidade com assinatura antiga
    calibration = database.get_user_calibration(user)
    if not calibration:
        raise ValueError(f"Usuário '{user}' náo encontrado na base de dados.")

    up_source = (
        calibration.get("up")
        or calibration.get("up_world")
        or [
            _safe_float(calibration.get("nx"), 0.0),
            _safe_float(calibration.get("ny"), -1.0),
            _safe_float(calibration.get("nz"), 0.0),
        ]
    )
    up = np.array(up_source, float)

    baseline_source = calibration.get("baseline") or calibration
    baseline = {
        "mu_pitch": _safe_float(baseline_source.get("mu_pitch")),
        "mu_yaw": _safe_float(baseline_source.get("mu_yaw")),
        "mu_roll": _safe_float(baseline_source.get("mu_roll")),
        "ybar0": _safe_float(baseline_source.get("ybar0")),
        "W0": _safe_float(baseline_source.get("W0"), 0.35),
        "z_chest0": _safe_float(baseline_source.get("z_chest0")),
        "L_tronco0": _safe_float(baseline_source.get("L_tronco0")),
        "trunk_pitch": _safe_float(baseline_source.get("trunk_pitch"), 0.0),
        "trunk_roll": _safe_float(baseline_source.get("trunk_roll"), 0.0),
    }

    fps_value = calibration.get("fps") or baseline_source.get("fps") or 30
    try:
        fps = int(float(fps_value))
    except (TypeError, ValueError):
        fps = 30

    return up, baseline, fps


def get_available_users():
    """Retorna lista de usuários disponíveis a partir do banco de dados."""
    try:
        return database.list_users()
    except Exception as exc:
        logger.error(f"Erro ao ler usuários do banco de dados: {exc}")
        return []


def obter_ponto_3d(depth_frame, intrinsics, px):
    """Obtém ponto 3D a partir de coordenadas 2D e profundidade"""
    u, v = int(px[0]), int(px[1])
    h, w = depth_frame.get_height(), depth_frame.get_width()
    if not (0 <= u < w and 0 <= v < h):
        return None
    d = depth_frame.get_distance(u, v)
    if d <= 0:
        return None
    return np.array(rs.rs2_deproject_pixel_to_point(intrinsics, [u, v], d), float)

def _norm(v, eps=1e-8):
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / (n + eps)

def corrigir_hip(px_hip, mask, offset=18):
    """
    Se o pixel do quadril estiver sobre a mesa (mask>0),
    move-o para alguns pixels ACIMA do topo da mesa na mesma coluna.
    """
    if mask is None or px_hip is None:
        return px_hip
    x, y = int(px_hip[0]), int(px_hip[1])
    h, w = mask.shape
    if 0 <= x < w and 0 <= y < h and mask[y, x] > 0:
        col = mask[:, x]
        ys = np.where(col > 0)[0]
        if ys.size > 0:
            y_top = int(ys[0])
            return (x, max(0, y_top - offset))
    return px_hip

def check_camera_connection():
    """Verifica se há  uma câmara RealSense conectada"""
    try:
        ctx = rs.context()
        devices = ctx.query_devices()
        
        if len(devices) == 0:
            logger.warning("Nenhuma câmara RealSense detetada")
            return False
        
        for device in devices:
            device_name = device.get_info(rs.camera_info.name)
            logger.info(f"câmara RealSense detetada: {device_name}")
            return True
            
        return False
    except Exception as e:
        logger.error(f"Erro ao verificar conexá£o da câmara: {e}")
        return False

# --------- Classe Principal ---------
class PostureAnalyzer:
    """Serviá§o de análise de postura em tempo real"""
    
    def __init__(self):
        self.pipeline = None
        self.detector = None
        self.pose = None
        self.current_user = None
        self.running = False
        self.thread = None
        self.calibrating = False
        self.calibration_data = None
        self.last_frame = None
        self.last_detection_result = None
        self.telemetry = None
        self.bad_posture_latch = None
        
        # Buffer para leituras de postura (batch insert)
        self.readings_buffer = []
        self.readings_buffer_size = 30  # Inserir a cada 30 leituras
        self.current_session_id = None

        self.mask_mesa = None
        self.up_estimated = None          # up_world estimado na calibração (fase 1)
        self.axes_accum_x = []            # acumula eixo tronco (x_ref)
        self.axes_accum_y = []            # acumula eixo ombros (y_ref)
        self.calib_phase = 1              # 1 = estimar up_world, 2 = coletar baseline
        self.calib_frames_target_phase1 = 30   # ~30 frames para estimar up_world
        self.calib_frames_target_phase2 = 90   # ~60-90 frames para baseline
        self.calib_frames_collected_phase1 = 0
        self.calib_frames_collected_phase2 = 0

    def start_analysis(self, user: str, socketio_instance):
        """Inicia análise para um usuário especifico"""
        if self.running:
            self.stop_analysis()
        
        if not check_camera_connection():
            logger.error("Tentativa de iniciar análise sem câmara conectada")
            return False
            
        try:
            up_world, baseline, fps_calib = load_user_row(user)
            self.current_user = user
            
            # Inicializar RealSense
            self.pipeline = rs.pipeline()
            config = rs.config()
            config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
            config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
            self.pipeline.start(config)
            self.align = rs.align(rs.stream.color)
            
            # Inicializar MediaPipe Pose
            mp_pose = mp.solutions.pose
            self.pose = mp_pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                enable_segmentation=True
            )
            logger.info("MediaPipe Pose inicializado")
            
            # Inicializar detector
            self.detector = PostureDetector(up_world, baseline, fps=fps_calib)

            # Carregar máscara da mesa se existir
            try:
                mask_path = "mask_mesa.npy"
                if os.path.exists(mask_path):
                    self.mask_mesa = np.load(mask_path)
                    logger.info(f"Máscara da mesa carregada: {mask_path}")
                else:
                    self.mask_mesa = None
                    logger.info("Nenhuma máscara da mesa encontrada (mask_mesa.npy).")
            except Exception as e:
                self.mask_mesa = None
                logger.warning(f"Falha ao carregar máscara da mesa: {e}")

            
            # Inicializar telemetria
            self.telemetry = {
                'standing_time': 0.0,
                'sitting_time': 0.0,
                'absence_time': 0.0,
                'pitch_on_time': 0.0,
                'yaw_on_time': 0.0,
                'roll_on_time': 0.0,
                'em_on_time': 0.0,
                'ed_on_time': 0.0,
                'trunk_pitch_on_time': 0.0,
                'trunk_roll_on_time': 0.0,
                'head_extension_on_time': 0.0,
                'bad_posture_time': 0.0,
                'last_standing': None,
                'last_sitting': None,
                'last_absence': None,
                'last_pitch_on': None,
                'last_trunk_roll_on': None,
                'last_trunk_pitch_on': None,
                'last_yaw_on': None,
                'last_roll_on': None,
                'last_em_on': None,
                'last_ed_on': None,
                'last_head_extension_on': None,
                'last_bad_posture_time': None,
                'start_time': time.time(),
                'frame_count': 0,
                'continuous_standing_time': 0.0,
                'max_continuous_standing': 0.0,
                'last_person_seen': time.time(),
                'absence_start': None,
                'pitch_alerts': 0,
                'yaw_alerts': 0,
                'roll_alerts': 0,
                'em_alerts': 0,
                'ed_alerts': 0,
                'head_extension_alerts': 0,
                'trunk_pitch_alerts': 0,
                'trunk_roll_alerts': 0,
                'pitch_diffs': [],
                'yaw_diffs': [],
                'roll_diffs': [],
                'em_values': [],
                'trunk_pitch_diffs': [],
                'trunk_roll_diffs': [],
                'ed_values': []
            }
            
            self.bad_posture_latch = Latch(on_thr=1.0, off_ratio=0.4, min_frames_on=5)
            self.running = True
            self.socketio = socketio_instance
            self.thread = self.socketio.start_background_task(target=self._analysis_loop)
            
            logger.info(f"análise iniciada para usuário: {user}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao iniciar análise: {e}")
            self.stop_analysis()
            return False
    
    def stop_analysis(self):
        """Para a analise"""
        self.running = False
        
        if self.telemetry:
            self.finalize_telemetry()
        
        if self.pipeline:
            try:
                self.pipeline.stop()
            except Exception:
                pass
        
        if self.pose:
            try:
                if hasattr(self.pose, 'close'):
                    self.pose.close()
            except Exception:
                pass
        
        self.pipeline = None
        self.detector = None
        self.pose = None
        self.last_frame = None
        self.last_detection_result = None
        self.telemetry = None
        self.bad_posture_latch = None
        logger.info("análise parada")
    
    def start_calibration(self, user: str, socketio_instance):
        """Inicia calibração para um novo usuário"""
        if self.running:
            self.stop_analysis()
        
        if not check_camera_connection():
            logger.error("Tentativa de iniciar calibração sem câmara conectada")
            return False
            
        try:
            self.current_user = user
            self.calibrating = True
            
            # Inicializar RealSense
            self.pipeline = rs.pipeline()
            config = rs.config()
            config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
            config.enable_stream(rs.stream.depth, 640, 480, rs.format.z16, 30)
            self.pipeline.start(config)
            self.align = rs.align(rs.stream.color)
            
            # Inicializar MediaPipe Pose
            mp_pose = mp.solutions.pose
            self.pose = mp_pose.Pose(
                static_image_mode=False,
                model_complexity=1,
                enable_segmentation=True
            )
            logger.info("MediaPipe Pose inicializado")

            # Carregar máscara da mesa se existir
            try:
                mask_path = "mask_mesa.npy"
                if os.path.exists(mask_path):
                    self.mask_mesa = np.load(mask_path)
                    logger.info(f"Máscara da mesa carregada: {mask_path}")
                else:
                    self.mask_mesa = None
                    logger.info("Nenhuma máscara da mesa encontrada (mask_mesa.npy).")
            except Exception as e:
                self.mask_mesa = None
                logger.warning(f"Falha ao carregar máscara da mesa: {e}")

            self.up_estimated = None
            self.axes_accum_x.clear()
            self.axes_accum_y.clear()
            self.calib_phase = 1
            self.calib_frames_collected_phase1 = 0
            self.calib_frames_collected_phase2 = 0
            
            # Inicializar dados de calibração
            self.calibration_data = {
                'pitchs': [], 'yaws': [], 'rolls': [],
                'W_list': [], 'ybar_list': [], 'z_chests': [],
                'frames_collected': 0,
                'frames_target': 120,
                'started': False
            }
            
            self.running = True
            self.socketio = socketio_instance
            self.thread = self.socketio.start_background_task(target=self._calibration_loop)
            
            logger.info(f"calibração iniciada para usuário: {user}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao iniciar calibração: {e}")
            self.stop_calibration()
            return False
    
    def stop_calibration(self):
        """Para a calibração"""
        self.calibrating = False
        self.running = False
        
        if self.pipeline:
            try:
                self.pipeline.stop()
            except Exception:
                pass
        
        if self.pose:
            try:
                if hasattr(self.pose, 'close'):
                    self.pose.close()
            except Exception:
                pass
        
        self.pipeline = None
        self.pose = None
        self.calibration_data = None
        self.last_frame = None
        self.last_detection_result = None
        logger.info("calibração parada")
    
    def save_calibration(self):
        """Salva os dados de calibracao no banco de dados."""
        if not self.calibration_data or not self.calibration_data.get('pitchs'):
            return False

        try:
            pitchs = self.calibration_data['pitchs']
            yaws = self.calibration_data['yaws']
            rolls = self.calibration_data['rolls']
            W_list = self.calibration_data['W_list']
            ybar_list = self.calibration_data['ybar_list']
            z_chests = self.calibration_data['z_chests']

            # usa o up_world estimado na FASE 1
            if self.up_estimated is None:
                logger.warning("up_world não estimado; fallback [0,-1,0].")
                up_world = np.array([0.0, -1.0, 0.0], float)
            else:
                up_world = np.asarray(self.up_estimated, float)

            # trunk baselines (foram calculados dentro do _collect_calibration_data? se não, calcule aqui)
            trunk_pitchs = self.calibration_data.get('trunk_pitchs', [])
            trunk_rolls  = self.calibration_data.get('trunk_rolls', [])
            # se não tiver, inicialize com 0
            mu_trunk_pitch = float(np.mean(trunk_pitchs)) if trunk_pitchs else 0.0
            mu_trunk_roll  = float(np.mean(trunk_rolls))  if trunk_rolls  else 0.0

            baseline = {
                "mu_pitch": float(np.mean(pitchs)),
                "mu_yaw": float(np.mean(yaws)),
                "mu_roll": float(np.mean(rolls)),
                "ybar0": float(np.median(ybar_list)) if ybar_list else 0.0,
                "W0": float(np.median(W_list)) if W_list else 0.35,
                "z_chest0": float(np.median(z_chests)) if z_chests else 0.0,
                "L_tronco0": 0.0,
                "trunk_pitch": mu_trunk_pitch,
                "trunk_roll":  mu_trunk_roll,
            }

            calibration_record = {
                "timestamp": int(time.time()),
                "up": up_world.tolist(),   # agora vem do tronco do usuário
                "baseline": baseline,
                "fps": 30,
                "notes": "Calibrado via frontend (up_world do tronco + máscara mesa)"
            }

            if database.create_user(self.current_user, calibration_record):
                logger.info(f"Calibração salva para usuário: {self.current_user}")
                return True

            logger.error(f"Falha ao salvar calibracao para usuario {self.current_user} no banco.")
            return False

        except Exception as e:
            logger.error(f"Erro ao salvar calibracao: {e}")
            return False

    def generate_frames(self):
        """Gera frames para o stream de vídeo com landmarks"""
        while not self.running:
            black_img = np.zeros((480, 640, 3), dtype=np.uint8)
            msg = 'Inicie a analise ou calibracao'
            (w, h), _ = cv2.getTextSize(msg, cv2.FONT_HERSHEY_SIMPLEX, 1, 2)
            cv2.putText(black_img, msg, ((640 - w) // 2, (480 - h) // 2),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            ret, buffer = cv2.imencode('.jpg', black_img)
            if not ret:
                time.sleep(0.5)
                continue
            frame_bytes = buffer.tobytes()
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
            time.sleep(0.5)

        while self.running:
            if self.last_frame is not None:
                try:
                    frame_to_show = self.last_frame.copy()

                    # ============ desenhar landmarks do MediaPipe ============
                    # if self.last_detection_result and self.last_detection_result.pose_landmarks:
                    #     try:
                    #         mp.solutions.drawing_utils.draw_landmarks(
                    #             frame_to_show,
                    #             self.last_detection_result.pose_landmarks,
                    #             mp.solutions.pose.POSE_CONNECTIONS,
                    #             landmark_drawing_spec=mp.solutions.drawing_styles.get_default_pose_landmarks_style()
                    #         )
                    #     except Exception as e:
                    #         logger.debug(f"Falha ao desenhar landmarks: {e}")

                    h, w = frame_to_show.shape[:2]

                    # ============ sobrepor máscara da mesa (vermelho translúcido) ============
                    # if hasattr(self, "mask_mesa") and self.mask_mesa is not None:
                    #     try:
                    #         mask_resized = self.mask_mesa
                    #         if mask_resized.shape != (h, w):
                    #             mask_resized = cv2.resize(mask_resized, (w, h), interpolation=cv2.INTER_NEAREST)

                    #         # cria um overlay vermelho translúcido (alpha = 0.35)
                    #         overlay = frame_to_show.copy()
                    #         overlay[mask_resized > 0] = (0, 0, 255)  # vermelho
                    #         frame_to_show = cv2.addWeighted(overlay, 0.35, frame_to_show, 0.65, 0)
                    #     except Exception as e:
                    #         logger.debug(f"Falha ao desenhar máscara da mesa: {e}")

                    # ============ desenhar linha dos ombros e vetor do tronco ============
                    try:
                        res = self.last_detection_result
                        if res and res.pose_landmarks:
                            lm = res.pose_landmarks.landmark
                            L = mp.solutions.pose.PoseLandmark

                            def px(idx):
                                return (int(lm[idx].x * w), int(lm[idx].y * h)), lm[idx].visibility

                            (px_LS, vls) = px(L.LEFT_SHOULDER.value)
                            (px_RS, vrs) = px(L.RIGHT_SHOULDER.value)
                            (px_LH, vlh) = px(L.LEFT_HIP.value)
                            (px_RH, vrh) = px(L.RIGHT_HIP.value)


                            # linha entre ombros (verde)
                            if vls > 0.5 and vrs > 0.5:
                                cv2.line(frame_to_show, px_LS, px_RS, (0, 255, 0), 2)
                                mid_shoulder = (
                                    int((px_LS[0] + px_RS[0]) / 2),
                                    int((px_LS[1] + px_RS[1]) / 2)
                                )
                                cv2.circle(frame_to_show, mid_shoulder, 5, (0, 255, 0), -1)

                                # linha do tronco (ombros → quadris)
                                if vlh > 0.5 and vrh > 0.5:
                                    px_RH = corrigir_hip(px_RH, self.mask_mesa, offset=18)
                                    px_LH = corrigir_hip(px_LH, self.mask_mesa, offset=18)
                                    mid_hip = (
                                        int((px_LH[0] + px_RH[0]) / 2),
                                        int((px_LH[1] + px_RH[1]) / 2)
                                    )
                                    cv2.line(frame_to_show, mid_shoulder, mid_hip, (255, 255, 0), 2)
                                    cv2.circle(frame_to_show, mid_hip, 5, (255, 255, 0), -1)
                                    cv2.putText(frame_to_show, "Tronco", mid_hip,
                                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 2)
                    except Exception as e:
                        logger.debug(f"Falha ao desenhar eixos: {e}")

                    # ============ codificar e enviar frame ============
                    ret, buffer = cv2.imencode('.jpg', frame_to_show)
                    if not ret:
                        continue
                    frame_bytes = buffer.tobytes()
                    yield (b'--frame\r\n'
                        b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

                except Exception as e:
                    logger.error(f"Erro ao gerar frame de vídeo: {e}")

            self.socketio.sleep(0.033)


    def _calibration_loop(self):
        """Loop de calibração com 2 fases:
        FASE 1: ~30 frames para estimar up_world pelo tronco (ombros->quadris)
        FASE 2: ~90 frames para coletar baselines usando o up_world estimado
        """
        mp_pose = mp.solutions.pose
        L = mp_pose.PoseLandmark
        last_fn = None

        # segurança: se a UI ainda não inicializou estes campos
        self.calibration_data.setdefault('trunk_pitchs', [])
        self.calibration_data.setdefault('trunk_rolls', [])
        # se o chamador não setou frames_target global, usamos soma das fases
        total_target = self.calib_frames_target_phase1 + self.calib_frames_target_phase2

        while self.running and self.calibrating:
            try:
                frames = self.pipeline.wait_for_frames()
                aligned = self.align.process(frames)
                color = aligned.get_color_frame()
                depth = aligned.get_depth_frame()
                if not color or not depth:
                    continue

                fn = color.get_frame_number()
                if last_fn is not None and fn == last_fn:
                    continue
                last_fn = fn

                bgr = np.asanyarray(color.get_data())
                self.last_frame = bgr.copy()
                h, w = bgr.shape[:2]
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)

                res = self.pose.process(rgb)
                self.last_detection_result = res
                lm = res.pose_landmarks.landmark if res.pose_landmarks else None

                # payload base
                collected_total = self.calib_frames_collected_phase1 + self.calib_frames_collected_phase2
                data = {
                    'timestamp': time.time(),
                    'user': self.current_user,
                    'status': 'waiting_person',
                    'message': 'Aguardando pessoa para calibração',
                    'calibration': {
                        'frames_collected': collected_total,
                        'frames_target': total_target,
                        'started': self.calibration_data.get('started', False),
                        'progress': (collected_total / total_target) * 100.0 if total_target > 0 else 0.0
                    }
                }

                if lm is None:
                    self.socketio.emit('calibration_data', data)
                    self.socketio.sleep(0.033)
                    continue

                def px(idx):
                    return (int(lm[idx].x * w), int(lm[idx].y * h)), lm[idx].visibility

                (px_LS, vls) = px(L.LEFT_SHOULDER.value)
                (px_RS, vrs) = px(L.RIGHT_SHOULDER.value)
                (px_LE, vle) = px(L.LEFT_EYE.value)
                (px_RE, vre) = px(L.RIGHT_EYE.value)
                (px_N,  vn ) = px(L.NOSE.value)
                (px_LH, vlh) = px(L.LEFT_HIP.value)
                (px_RH, vrh) = px(L.RIGHT_HIP.value)

                # Corrigir hips com a máscara (se existir)
                if self.mask_mesa is not None:
                    if self.mask_mesa.shape != (h, w):
                        self.mask_mesa = cv2.resize(self.mask_mesa, (w, h), interpolation=cv2.INTER_NEAREST)
                    if vlh >= 0.5:
                        px_LH = corrigir_hip(px_LH, self.mask_mesa, offset=18)
                    if vrh >= 0.5:
                        px_RH = corrigir_hip(px_RH, self.mask_mesa, offset=18)

                intr = depth.profile.as_video_stream_profile().intrinsics

                if vls < 0.5 or vrs < 0.5:
                    data['status'] = 'unreliable_shoulders'
                    data['message'] = 'Ombros não detectados'
                    self.socketio.emit('calibration_data', data)
                    self.socketio.sleep(0.033)
                    continue

                # Deprojetar
                LS = obter_ponto_3d(depth, intr, px_LS)
                RS = obter_ponto_3d(depth, intr, px_RS)
                LH = obter_ponto_3d(depth, intr, px_LH) if vlh >= 0.5 else None
                RH = obter_ponto_3d(depth, intr, px_RH) if vrh >= 0.5 else None

                # Cabeça (olhos -> média, fallback nariz)
                H = None
                if vle > 0.5 and vre > 0.5:
                    EL = obter_ponto_3d(depth, intr, px_LE)
                    ER = obter_ponto_3d(depth, intr, px_RE)
                    if EL is not None and ER is not None:
                        H = 0.5 * (EL + ER)
                if H is None and vn > 0.5:
                    H = obter_ponto_3d(depth, intr, px_N)

                if any(v is None for v in [LS, RS, LH, RH, H]):
                    data['status'] = 'insufficient_3d'
                    data['message'] = 'Dados 3D insuficientes (ombros/hips/cabeça)'
                    self.socketio.emit('calibration_data', data)
                    self.socketio.sleep(0.033)
                    continue

                # Pessoa presente e válida
                data['status'] = 'person_detected'
                data['message'] = 'Pessoa detectada - Pronto para calibrar'

                # Só começa a coletar se usuário clicou "Começar" no frontend
                if not self.calibration_data.get('started', False):
                    self.socketio.emit('calibration_data', data)
                    self.socketio.sleep(0.033)
                    continue

                # -------------------------------------------------------
                # FASE 1: estimar up_world (tronco) por ~30 frames
                # -------------------------------------------------------
                if self.calib_phase == 1:
                    mid_shoulder = 0.5 * (LS + RS)
                    mid_hip      = 0.5 * (LH + RH)

                    x_ref_i = _norm(mid_shoulder - mid_hip)  # "tronco" (ombros -> quadris)
                    y_ref_i = _norm(RS - LS)                 # "ombros" (esq->dir)

                    self.axes_accum_x.append(x_ref_i)
                    self.axes_accum_y.append(y_ref_i)
                    self.calib_frames_collected_phase1 += 1

                    # atualizar barra de progresso
                    collected_total = self.calib_frames_collected_phase1 + self.calib_frames_collected_phase2
                    data['status'] = 'calibrating'
                    data['message'] = f"Estimando up_world... ({self.calib_frames_collected_phase1}/{self.calib_frames_target_phase1})"
                    data['calibration']['frames_collected'] = collected_total
                    data['calibration']['frames_target'] = total_target
                    data['calibration']['progress'] = (collected_total / total_target) * 100.0

                    # concluiu FASE 1?
                    if self.calib_frames_collected_phase1 >= self.calib_frames_target_phase1:
                        # médias + Gram-Schmidt leve
                        x_mean = _norm(np.mean(np.stack(self.axes_accum_x, axis=0), axis=0))
                        y_mean = _norm(np.mean(np.stack(self.axes_accum_y, axis=0), axis=0))
                        y_ref = _norm(y_mean)                                   # eixo ombros (lateral)
                        x_ref = _norm(x_mean - np.dot(x_mean, y_ref) * y_ref)   # tronco projetado no plano ⟂ a y_ref
                        z_ref = _norm(np.cross(x_ref, y_ref))                   # perpendicular (destro)

                        # sua convenção: up_world := x_ref (tronco)
                        self.up_estimated = x_ref.copy()
                        self.calib_phase = 2
                        logger.info(f"up_world estimado (FASE 1): {self.up_estimated}")

                    self.socketio.emit('calibration_data', data)
                    self.socketio.sleep(0.033)
                    continue  # volta p/ próximo frame

                # -------------------------------------------------------
                # FASE 2: coletar baselines usando o up_world estimado
                # -------------------------------------------------------
                if self.calib_phase == 2:
                    # segurança: se por algum motivo up não veio, fallback
                    up_cam = self.up_estimated if self.up_estimated is not None else np.array([0.0, -1.0, 0.0])

                    # métricas do tronco (para baseline)
                    mid_shoulder = 0.5 * (LS + RS)
                    mid_hip      = 0.5 * (LH + RH)
                    trunk_vec    = _norm(mid_shoulder - mid_hip)
                    trunk_pitch  = float(np.degrees(np.arcsin(np.clip(trunk_vec[2], -1, 1))))
                    trunk_roll   = float(np.degrees(np.arcsin(np.clip(trunk_vec[0], -1, 1))))
                    self.calibration_data['trunk_pitchs'].append(trunk_pitch)
                    self.calibration_data['trunk_rolls'].append(trunk_roll)

                    # coleta dos baselines cabeça/ombros/peito com up_cam estimado
                    self._collect_calibration_data(LS, RS, H, up_vec=self.up_estimated, LH=LH, RH=RH)

                    self.calib_frames_collected_phase2 += 1
                    collected_total = self.calib_frames_collected_phase1 + self.calib_frames_collected_phase2

                    data['status'] = 'calibrating'
                    data['message'] = f"Coletando dados baseline... ({self.calib_frames_collected_phase2}/{self.calib_frames_target_phase2})"
                    data['calibration']['frames_collected'] = collected_total
                    data['calibration']['frames_target'] = total_target
                    data['calibration']['progress'] = (collected_total / total_target) * 100.0

                    if self.calib_frames_collected_phase2 >= self.calib_frames_target_phase2:
                        data['status'] = 'calibration_complete'
                        data['message'] = 'Calibração completa! Clique em Salvar.'

                # enviar ao frontend
                self.socketio.emit('calibration_data', data)
                self.socketio.sleep(0.033)

            except Exception as e:
                logger.error(f"Erro no loop de calibração: {e}")
                data = {
                    'timestamp': time.time(),
                    'user': self.current_user,
                    'status': 'error',
                    'message': f'Erro: {str(e)}'
                }
                self.socketio.emit('calibration_data', data)
                self.socketio.sleep(1)

    
    def _collect_calibration_data(self, LS, RS, H, up_vec, LH=None, RH=None):
        """
        Coleta amostras de calibração.
        - LS, RS, H, LH, RH: pontos 3D (np.array shape (3,))
        - up_vec: vetor 'para cima' a usar nesta fase (fase 1: up_cam; fase 2: self.up_estimated)
        """
        try:
            from posture_detector import _norm

            # ---- entradas seguras ----
            LS = np.asarray(LS, dtype=float)
            RS = np.asarray(RS, dtype=float)
            H  = np.asarray(H,  dtype=float)
            up = _norm(np.asarray(up_vec, dtype=float))

            # ---- eixos locais do tronco (ombros) ----
            x_body = _norm(RS - LS)                 # eixo lateral (E->D)
            z_body = _norm(np.cross(x_body, up))    # "frente" do tronco
            y_body = _norm(np.cross(z_body, x_body))# "cima" do tronco

            # orienta y_body para apontar da cintura para a cabeça
            S = 0.5 * (LS + RS)                     # centro dos ombros
            if np.dot(y_body, (H - S)) < 0:
                y_body = -y_body
                z_body = _norm(np.cross(x_body, y_body))

            # ---- peito sintético ----
            W = float(np.linalg.norm(RS - LS))
            W_eff = W if W > 1e-6 else 0.35
            C = S - 0.40 * y_body * W_eff

            # ---- cabeça no plano sagital ----
            u = H - C
            if np.dot(u, z_body) < 0:
                z_body = -z_body
                y_body = _norm(np.cross(z_body, x_body))

            # projeção no plano sagital (remove componente lateral)
            u_lat = np.dot(u, x_body) * x_body
            u_sag = u - u_lat
            n_us = np.linalg.norm(u_sag)
            if n_us > 1e-8:
                u_sag = u_sag / n_us
            else:
                # fallback: se não houver componente sagital suficiente, aborta a amostra
                return

            ty = float(np.dot(u_sag, y_body))
            tz = float(np.dot(u_sag, z_body))

            pitch = float(np.degrees(np.arctan2(tz, ty)))
            # yaw (aprox) relativo ao frame da câmera
            yaw   = float(np.degrees(np.arctan2(np.dot(z_body, [1,0,0]), np.dot(z_body, [0,0,1]))))
            # roll: inclinação lateral da linha dos ombros versus up
            roll  = float(np.degrees(np.arcsin(np.clip(np.dot(x_body, up), -1.0, 1.0))))

            ybar = float(0.5 * (LS[1] + RS[1]))

            # ---- acúmulo de medidas base ----
            self.calibration_data['pitchs'].append(pitch)
            self.calibration_data['yaws'].append(yaw)
            self.calibration_data['rolls'].append(roll)
            self.calibration_data['W_list'].append(W)
            self.calibration_data['ybar_list'].append(ybar)
            self.calibration_data['z_chests'].append(float(C[2]))

            # ---- medidas do tronco (se LH e RH disponíveis) ----
            if LH is not None and RH is not None:
                LH = np.asarray(LH, dtype=float)
                RH = np.asarray(RH, dtype=float)
                mid_hip = 0.5 * (LH + RH)
                trunk_vec = _norm(S - mid_hip)  # direção ombros -> quadris (y corporal)

                # pitch do tronco: componente Z (aprox. avanço/recúo)
                trunk_pitch = float(np.degrees(np.arcsin(np.clip(trunk_vec[2], -1.0, 1.0))))
                # roll do tronco: componente X (aprox. inclinação lateral)
                trunk_roll  = float(np.degrees(np.arcsin(np.clip(trunk_vec[0], -1.0, 1.0))))

                # garante listas
                if 'trunk_pitchs' not in self.calibration_data:
                    self.calibration_data['trunk_pitchs'] = []
                if 'trunk_rolls' not in self.calibration_data:
                    self.calibration_data['trunk_rolls'] = []

                self.calibration_data['trunk_pitchs'].append(trunk_pitch)
                self.calibration_data['trunk_rolls'].append(trunk_roll)

            # contador de frames coletados desta fase
            self.calibration_data['frames_collected'] += 1

        except Exception as e:
            logger.error(f"Erro ao coletar dados de calibracao: {e}")


    def _analysis_loop(self):
        """Loop principal de análise com telemetria avançada"""
        mp_pose = mp.solutions.pose
        L = mp_pose.PoseLandmark
        last_fn = None
        last_ts = None

        while self.running:
            try:
                frames = self.pipeline.wait_for_frames()
                aligned = self.align.process(frames)
                color = aligned.get_color_frame()
                depth = aligned.get_depth_frame()
                
                if not color or not depth:
                    continue
                
                fn = color.get_frame_number()
                if last_fn is not None and fn == last_fn:
                    continue
                last_fn = fn
                
                ts_ms = color.get_timestamp()
                dt = 0.0 if last_ts is None else max(0.0, (ts_ms - last_ts)/1000.0)
                last_ts = ts_ms

                current_time = time.time()
                
                if self.telemetry['absence_start'] is not None and current_time - self.telemetry['absence_start'] > 10:
                    self.telemetry['continuous_standing_time'] = 0.0

                bgr = np.asanyarray(color.get_data())
                self.last_frame = bgr.copy()
                h, w = bgr.shape[:2]
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                
                res = self.pose.process(rgb)
                self.last_detection_result = res
                lm = res.pose_landmarks.landmark if res.pose_landmarks else None

                if lm is None:
                    if self.telemetry['last_absence'] is None:
                        self.telemetry['last_absence'] = current_time
                    if self.telemetry['absence_start'] is None:
                        self.telemetry['absence_start'] = current_time
                    
                    data = {
                        'timestamp': current_time,
                        'user': self.current_user,
                        'status': 'no_person',
                        'message': 'Sem pessoa detectada'
                    }
                    self.socketio.emit('posture_data', data)
                    self.socketio.sleep(0.033)
                    continue

                if self.telemetry['last_absence'] is not None:
                    self.telemetry['absence_time'] += current_time - self.telemetry['last_absence']
                    self.telemetry['last_absence'] = None
                self.telemetry['last_person_seen'] = current_time
                self.telemetry['absence_start'] = None

                def px(idx):
                    return (int(lm[idx].x*w), int(lm[idx].y*h)), lm[idx].visibility
                
                (px_LS, vls) = px(L.LEFT_SHOULDER.value)
                (px_RS, vrs) = px(L.RIGHT_SHOULDER.value)
                (px_LE, vle) = px(L.LEFT_EYE.value)
                (px_RE, vre) = px(L.RIGHT_EYE.value)
                (px_N, vn) = px(L.NOSE.value)
                (px_LW, vlw) = px(L.LEFT_WRIST.value)
                (px_RW, vrw) = px(L.RIGHT_WRIST.value)

                (px_LH, vlh) = px(L.LEFT_HIP.value)
                (px_RH, vrh) = px(L.RIGHT_HIP.value)

                if self.mask_mesa is not None:
                    if self.mask_mesa.shape != (h, w):
                        self.mask_mesa = cv2.resize(self.mask_mesa, (w, h), interpolation=cv2.INTER_NEAREST)
                    if vlh >= 0.5:
                        px_LH = corrigir_hip(px_LH, self.mask_mesa, offset=18)
                    if vrh >= 0.5:
                        px_RH = corrigir_hip(px_RH, self.mask_mesa, offset=18)

                

                
                intr = depth.profile.as_video_stream_profile().intrinsics
                
                if vls < 0.5 or vrs < 0.5:
                    data = {
                        'timestamp': current_time,
                        'user': self.current_user,
                        'status': 'unreliable_shoulders',
                        'message': 'Ombros ná£o confiá veis'
                    }
                    self.socketio.emit('posture_data', data)
                    self.socketio.sleep(0.033)
                    continue

                LS = obter_ponto_3d(depth, intr, px_LS)
                RS = obter_ponto_3d(depth, intr, px_RS)
                LW = obter_ponto_3d(depth, intr, px_LW) if vlw > 0.5 else None
                RW = obter_ponto_3d(depth, intr, px_RW) if vrw > 0.5 else None
                LH = obter_ponto_3d(depth, intr, px_LH) if vlh >= 0.5 else None
                RH = obter_ponto_3d(depth, intr, px_RH) if vrh >= 0.5 else None

                H = None
                if vle > 0.5 and vre > 0.5:
                    EL = obter_ponto_3d(depth, intr, px_LE)
                    ER = obter_ponto_3d(depth, intr, px_RE)
                    if EL is not None and ER is not None:
                        H = 0.5*(EL+ER)
                if H is None and vn > 0.5:
                    H = obter_ponto_3d(depth, intr, px_N)

                if any(v is None for v in [LS, RS, H]):
                    data = {
                        'timestamp': current_time,
                        'user': self.current_user,
                        'status': 'insufficient_3d',
                        'message': 'Dados 3D insuficientes'
                    }
                    self.socketio.emit('posture_data', data)
                    self.socketio.sleep(0.033)
                    continue

                # Detectar se mãos estão acima dos ombros
                arms_up = False
                if (LW is not None and LW[1] < LS[1]) or (RW is not None and RW[1] < RS[1]):
                    arms_up = True

                out = self.detector.step(LS, RS, H, LH=LH, RH=RH, arms_up=arms_up)

                self.telemetry['frame_count'] += 1

                if out['standing']:
                    # Usar diferença com sinal para pitch (positivo=frente, negativo=trás)
                    diff_pitch = angular_diff(out['pitch'], self.detector.mu_pitch)
                    diff_yaw = angular_diff(out['yaw'], self.detector.mu_yaw)
                    diff_roll = angular_diff(out['roll'], self.detector.mu_roll)
                    
                    # Calcular diferenças do tronco com sinal
                    diff_trunk_pitch = None
                    diff_trunk_roll = None
                    if out['trunk_pitch'] is not None:
                        diff_trunk_pitch = angular_diff(out['trunk_pitch'], self.detector.mu_trunk_pitch)
                    if out['trunk_roll'] is not None:
                        diff_trunk_roll = out['trunk_roll'] - self.detector.mu_trunk_roll

                    self.telemetry['pitch_diffs'].append(diff_pitch)
                    self.telemetry['yaw_diffs'].append(diff_yaw)
                    self.telemetry['roll_diffs'].append(diff_roll)
                    if diff_trunk_pitch is not None:
                        self.telemetry['trunk_pitch_diffs'].append(diff_trunk_pitch)
                    if diff_trunk_roll is not None:
                        self.telemetry['trunk_roll_diffs'].append(diff_trunk_roll)
                    self.telemetry['em_values'].append(out['em'])
                    self.telemetry['ed_values'].append(abs(out['ed']))
                    
                    # Coletar leitura para salvar no banco de dados
                    self._collect_posture_reading(out, current_time, diff_pitch, diff_yaw, diff_roll, diff_trunk_pitch, diff_trunk_roll)

                if out['standing']:
                    self.telemetry['continuous_standing_time'] += dt
                else:
                    self.telemetry['continuous_standing_time'] = 0.0

                self.telemetry['max_continuous_standing'] = max(
                    self.telemetry['max_continuous_standing'],
                    self.telemetry['continuous_standing_time']
                )

                if out['standing']:
                    if self.telemetry['last_sitting'] is not None:
                        self.telemetry['sitting_time'] += current_time - self.telemetry['last_sitting']
                        self.telemetry['last_sitting'] = None
                    if self.telemetry['last_standing'] is None:
                        self.telemetry['last_standing'] = current_time
                else:
                    if self.telemetry['last_standing'] is not None:
                        self.telemetry['standing_time'] += current_time - self.telemetry['last_standing']
                        self.telemetry['last_standing'] = None
                    if self.telemetry['last_sitting'] is None:
                        self.telemetry['last_sitting'] = current_time

                # Eventos - só quando em pé
                if out['standing']:
                    ev = out['events']

                    any_alert_active = ev['pitch_on'] or ev['yaw_on'] or ev['roll_on'] or ev['em_on'] or ev['ed_on'] or ev['trunk_roll_on'] or ev['trunk_pitch_on']
                    bad_posture_active = self.bad_posture_latch.step(1.0 if any_alert_active else 0.0, cond=True)
                    
                    # Debug: imprimir eventos ativos
                
                    if bad_posture_active:
                        if self.telemetry['last_bad_posture_time'] is not None:
                            time_diff = current_time - self.telemetry['last_bad_posture_time']
                            self.telemetry['bad_posture_time'] += time_diff
                        self.telemetry['last_bad_posture_time'] = current_time
                    else:
                        self.telemetry['last_bad_posture_time'] = None

                    # Contar alertas
                    if ev['pitch_on']:
                        if self.telemetry['last_pitch_on'] is None:
                            self.telemetry['last_pitch_on'] = current_time
                            self.telemetry['pitch_alerts'] += 1
                    else:
                        if self.telemetry['last_pitch_on'] is not None:
                            self.telemetry['pitch_on_time'] += current_time - self.telemetry['last_pitch_on']
                            self.telemetry['last_pitch_on'] = None

                    if ev['yaw_on']:
                        if self.telemetry['last_yaw_on'] is None:
                            self.telemetry['last_yaw_on'] = current_time
                            self.telemetry['yaw_alerts'] += 1
                    else:
                        if self.telemetry['last_yaw_on'] is not None:
                            self.telemetry['yaw_on_time'] += current_time - self.telemetry['last_yaw_on']
                            self.telemetry['last_yaw_on'] = None

                    if ev['roll_on']:
                        if self.telemetry['last_roll_on'] is None:
                            self.telemetry['last_roll_on'] = current_time
                            self.telemetry['roll_alerts'] += 1
                    else:
                        if self.telemetry['last_roll_on'] is not None:
                            self.telemetry['roll_on_time'] += current_time - self.telemetry['last_roll_on']
                            self.telemetry['last_roll_on'] = None

                    if ev['em_on']:
                        if self.telemetry['last_em_on'] is None:
                            self.telemetry['last_em_on'] = current_time
                            self.telemetry['em_alerts'] += 1
                    else:
                        if self.telemetry['last_em_on'] is not None:
                            self.telemetry['em_on_time'] += current_time - self.telemetry['last_em_on']
                            self.telemetry['last_em_on'] = None

                    if ev['trunk_pitch_on']:
                        if self.telemetry['last_trunk_pitch_on'] is None:
                            self.telemetry['last_trunk_pitch_on'] = current_time
                            self.telemetry['trunk_pitch_alerts'] += 1
                    else:
                        if self.telemetry['last_trunk_pitch_on'] is not None:
                            self.telemetry['trunk_pitch_on_time'] += current_time - self.telemetry['last_trunk_pitch_on']
                            self.telemetry['last_trunk_pitch_on'] = None
                    
                    if ev['trunk_roll_on']:
                        if self.telemetry['last_trunk_roll_on'] is None:
                            self.telemetry['last_trunk_roll_on'] = current_time
                            self.telemetry['trunk_roll_alerts'] += 1
                    else:
                        if self.telemetry['last_trunk_roll_on'] is not None:
                            self.telemetry['trunk_roll_on_time'] += current_time - self.telemetry['last_trunk_roll_on']
                            self.telemetry['last_trunk_roll_on'] = None

                    if ev['ed_on']:
                        if self.telemetry['last_ed_on'] is None:
                            self.telemetry['last_ed_on'] = current_time
                            self.telemetry['ed_alerts'] += 1
                    else:
                        if self.telemetry['last_ed_on'] is not None:
                            self.telemetry['ed_on_time'] += current_time - self.telemetry['last_ed_on']
                            self.telemetry['last_ed_on'] = None

                    # Preparar dados para envio
                    from utils import convert_numpy_types
                    
                    data = {
                        'timestamp': current_time,
                        'user': self.current_user,
                        'status': 'analyzing',
                        'standing': True,
                        'position': 'Em pé',
                        'metrics': {
                            'pitch': round(diff_pitch, 1),
                            'yaw': round(diff_yaw, 1),
                            'roll': round(diff_roll, 1),
                            'elevation': round(out['em']*100, 1),
                            'asymmetry': round(abs(out['ed'])*100, 1),
                            'shoulder_width': int(out['W']),
                            'trunk_pitch': round(diff_trunk_pitch, 1) if diff_trunk_pitch is not None else None,
                            'trunk_roll': round(diff_trunk_roll, 1) if diff_trunk_roll is not None else None,
                        },
                        'events': out['events'],
                        'telemetry': {
                            'session_duration': current_time - self.telemetry['start_time'],
                            'standing_time': self.telemetry['standing_time'] + (current_time - self.telemetry['last_standing'] if self.telemetry['last_standing'] else 0),
                            'sitting_time': self.telemetry['sitting_time'],
                            'bad_posture_time': self.telemetry['bad_posture_time'],
                            'continuous_standing_time': self.telemetry['continuous_standing_time'],
                            'max_continuous_standing': self.telemetry['max_continuous_standing'],
                            'total_alerts': (self.telemetry['pitch_alerts'] + self.telemetry['yaw_alerts'] +
                                           self.telemetry['roll_alerts'] + self.telemetry['em_alerts'] +
                                           self.telemetry['ed_alerts']),
                            'bad_posture_active': bad_posture_active
                        },
                        'gate_features': out['gate_features']
                    }
                else:
                    # Quando sentado, resetar eventos
                    self.telemetry['last_pitch_on'] = None
                    self.telemetry['last_yaw_on'] = None
                    self.telemetry['last_roll_on'] = None
                    self.telemetry['last_em_on'] = None
                    self.telemetry['last_ed_on'] = None
                    self.telemetry['last_trunk_pitch_on'] = None
                    self.telemetry['last_trunk_roll_on'] = None


                    self.bad_posture_latch.on = False
                    self.bad_posture_latch.c = 0
                    self.telemetry['last_bad_posture_time'] = None

                    from utils import convert_numpy_types
                    
                    data = {
                        'timestamp': current_time,
                        'user': self.current_user,
                        'status': 'position_detected',
                        'standing': False,
                        'position': 'Sentado',
                        'message': 'usuário sentado. Levante-se para análise de postura.',
                        'telemetry': {
                            'session_duration': current_time - self.telemetry['start_time'],
                            'standing_time': self.telemetry['standing_time'],
                            'sitting_time': self.telemetry['sitting_time'] + (current_time - self.telemetry['last_sitting'] if self.telemetry['last_sitting'] else 0),
                            'bad_posture_time': self.telemetry['bad_posture_time'],
                            'continuous_standing_time': self.telemetry['continuous_standing_time'],
                            'max_continuous_standing': self.telemetry['max_continuous_standing'],
                            'total_alerts': (self.telemetry['pitch_alerts'] + self.telemetry['yaw_alerts'] +
                                           self.telemetry['roll_alerts'] + self.telemetry['em_alerts'] +
                                           self.telemetry['ed_alerts']),
                            'bad_posture_active': False
                        },
                        'gate_features': out['gate_features']
                    }
                
                from utils import convert_numpy_types
                data_converted = convert_numpy_types(data)
                self.socketio.emit('posture_data', data_converted)
                self.socketio.sleep(0.033)
                
            except Exception as e:
                logger.error(f"Erro no loop de análise: {e}")
                data = {
                    'timestamp': time.time(),
                    'user': self.current_user,
                    'status': 'error',
                    'message': f'Erro: {str(e)}'
                }
                self.socketio.emit('posture_data', data)
                self.socketio.sleep(1)
    
    def _build_session_summary(self, end_time, bag_path=""):
        telemetry = self.telemetry or {}
        total_duration = max(end_time - telemetry.get('start_time', end_time), 0.0)

        def calc_stats(values):
            if not values:
                return {"mean": 0.0, "min": 0.0, "max": 0.0}
            arr = np.asarray(values, dtype=float)
            return {
                "mean": float(np.mean(arr)),
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
            }

        pitch_stats = calc_stats(telemetry.get('pitch_diffs', []))
        yaw_stats = calc_stats(telemetry.get('yaw_diffs', []))
        roll_stats = calc_stats(telemetry.get('roll_diffs', []))
        em_stats = calc_stats(telemetry.get('em_values', []))
        ed_stats = calc_stats(telemetry.get('ed_values', []))
        trunk_pitch_stats = calc_stats(telemetry.get('trunk_pitch_diffs', []))
        trunk_roll_stats = calc_stats(telemetry.get('trunk_roll_diffs', []))

        standing_time = float(telemetry.get('standing_time', 0.0))
        sitting_time = float(telemetry.get('sitting_time', 0.0))
        absence_time = float(telemetry.get('absence_time', 0.0))
        total_bad_posture_time = float(telemetry.get('bad_posture_time', 0.0))

        total_alerts = (
            telemetry.get('pitch_alerts', 0)
            + telemetry.get('yaw_alerts', 0)
            + telemetry.get('roll_alerts', 0)
            + telemetry.get('em_alerts', 0)
            + telemetry.get('ed_alerts', 0)
            + telemetry.get('trunk_pitch_alerts', 0)
            + telemetry.get('trunk_roll_alerts', 0)
        )

        frames_processed = int(telemetry.get('frame_count', 0))
        fps_average = round(frames_processed / total_duration, 2) if total_duration > 0 else 0

        session_data = {
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(end_time)),
            'user': self.current_user,
            'bag_file': os.path.basename(bag_path) if bag_path else '',
            'session_duration_seconds': round(total_duration, 2),
            'frames_processed': frames_processed,
            'fps_average': fps_average,
            'standing_time_seconds': round(standing_time, 2),
            'sitting_time_seconds': round(sitting_time, 2),
            'absence_time_seconds': round(absence_time, 2),
            'standing_percentage': round((standing_time / total_duration) * 100, 2) if total_duration > 0 else 0,
            'sitting_percentage': round((sitting_time / total_duration) * 100, 2) if total_duration > 0 else 0,
            'absence_percentage': round((absence_time / total_duration) * 100, 2) if total_duration > 0 else 0,
            'total_alerts': int(total_alerts),
            'pitch_alerts': int(telemetry.get('pitch_alerts', 0)),
            'yaw_alerts': int(telemetry.get('yaw_alerts', 0)),
            'roll_alerts': int(telemetry.get('roll_alerts', 0)),
            'trunk_pitch_alerts': int(telemetry.get('trunk_pitch_alerts', 0)),
            'trunk_roll_alerts': int(telemetry.get('trunk_roll_alerts', 0)),
            'em_alerts': int(telemetry.get('em_alerts', 0)),
            'ed_alerts': int(telemetry.get('ed_alerts', 0)),
            'total_bad_posture_time_seconds': round(total_bad_posture_time, 2),
            'bad_posture_percentage': round((total_bad_posture_time / total_duration) * 100, 2) if total_duration > 0 else 0,
            'pitch_on_time_seconds': round(float(telemetry.get('pitch_on_time', 0.0)), 2),
            'yaw_on_time_seconds': round(float(telemetry.get('yaw_on_time', 0.0)), 2),
            'roll_on_time_seconds': round(float(telemetry.get('roll_on_time', 0.0)), 2),
            'em_on_time_seconds': round(float(telemetry.get('em_on_time', 0.0)), 2),
            'ed_on_time_seconds': round(float(telemetry.get('ed_on_time', 0.0)), 2),
            'pitch_mean_diff': round(pitch_stats['mean'], 2),
            'pitch_min_diff': round(pitch_stats['min'], 2),
            'pitch_max_diff': round(pitch_stats['max'], 2),
            'yaw_mean_diff': round(yaw_stats['mean'], 2),
            'yaw_min_diff': round(yaw_stats['min'], 2),
            'yaw_max_diff': round(yaw_stats['max'], 2),
            'roll_mean_diff': round(roll_stats['mean'], 2),
            'roll_min_diff': round(roll_stats['min'], 2),
            'roll_max_diff': round(roll_stats['max'], 2),
            'trunk_pitch_mean_diff': round(trunk_pitch_stats['mean'], 2),
            'trunk_pitch_min_diff': round(trunk_pitch_stats['min'], 2),
            'trunk_pitch_max_diff': round(trunk_pitch_stats['max'], 2),
            'trunk_roll_mean_diff': round(trunk_roll_stats['mean'], 2),
            'trunk_roll_min_diff': round(trunk_roll_stats['min'], 2),
            'trunk_roll_max_diff': round(trunk_roll_stats['max'], 2),
            'em_mean': round(em_stats['mean'], 3),
            'em_min': round(em_stats['min'], 3),
            'em_max': round(em_stats['max'], 3),
            'ed_mean': round(ed_stats['mean'], 3),
            'ed_min': round(ed_stats['min'], 3),
            'ed_max': round(ed_stats['max'], 3),
            'max_continuous_standing_seconds': round(float(telemetry.get('max_continuous_standing', 0.0)), 2),
            'alerts_per_minute': round(total_alerts / (total_duration / 60.0), 2) if total_duration > 0 else 0,
        }
        return session_data

    def _collect_posture_reading(self, out, timestamp, diff_pitch, diff_yaw, diff_roll, diff_trunk_pitch, diff_trunk_roll):
        """
        Coleta uma leitura de postura para salvar no banco de dados.
        Acumula em buffer e insere em lote quando atingir o tamanho do buffer.
        """
        try:
            # Obter user_id (se ainda não temos)
            if self.current_session_id is None:
                user_id = database.get_user_id(self.current_user)
                if user_id is None:
                    return
                # Criar sessão temporária (será atualizada no finalize_telemetry)
                self.current_session_id = database.create_session(user_id, {})
            
            raw = out.get('raw_values', {})
            ev = out.get('events', {})
            
            reading = {
                'user_id': database.get_user_id(self.current_user),
                'session_id': self.current_session_id,
                'timestamp': timestamp,
                'frame_number': self.telemetry['frame_count'],
                # Valores brutos
                'pitch_raw': raw.get('pitch'),
                'yaw_raw': raw.get('yaw'),
                'roll_raw': raw.get('roll'),
                'trunk_pitch_raw': raw.get('trunk_pitch'),
                'trunk_roll_raw': raw.get('trunk_roll'),
                'em_raw': raw.get('em'),
                'ed_raw': raw.get('ed'),
                # Valores filtrados
                'pitch_filtered': out.get('pitch'),
                'yaw_filtered': out.get('yaw'),
                'roll_filtered': out.get('roll'),
                'trunk_pitch_filtered': out.get('trunk_pitch'),
                'trunk_roll_filtered': out.get('trunk_roll'),
                'em_filtered': out.get('em'),
                'ed_filtered': out.get('ed'),
                # Diferenças
                'pitch_diff': diff_pitch,
                'yaw_diff': diff_yaw,
                'roll_diff': diff_roll,
                'trunk_pitch_diff': diff_trunk_pitch,
                'trunk_roll_diff': diff_trunk_roll,
                # Outros
                'shoulder_width': out.get('W'),
                # Eventos
                'pitch_on': ev.get('pitch_on', False),
                'yaw_on': ev.get('yaw_on', False),
                'roll_on': ev.get('roll_on', False),
                'trunk_pitch_on': ev.get('trunk_pitch_on', False),
                'trunk_roll_on': ev.get('trunk_roll_on', False),
                'em_on': ev.get('em_on', False),
                'ed_on': ev.get('ed_on', False),
                'head_extension_on': ev.get('head_extension_on', False),
            }
            
            self.readings_buffer.append(reading)
            
            # Inserir em lote quando buffer atingir o tamanho
            if len(self.readings_buffer) >= self.readings_buffer_size:
                self._flush_readings_buffer()
                
        except Exception as e:
            logger.error(f"Erro ao coletar leitura de postura: {e}")
    
    def _flush_readings_buffer(self):
        """Insere todas as leituras do buffer no banco de dados."""
        if not self.readings_buffer:
            return
        
        try:
            database.insert_posture_readings_batch(self.readings_buffer)
            logger.debug(f"Inseridas {len(self.readings_buffer)} leituras de postura no banco.")
            self.readings_buffer.clear()
        except Exception as e:
            logger.error(f"Erro ao inserir leituras em lote: {e}")

    def finalize_telemetry(self):
        """Finaliza telemetria e persiste relatorio no banco de dados."""
        if not self.telemetry:
            return None

        try:
            end_time = time.time()

            if self.telemetry['last_standing'] is not None:
                self.telemetry['standing_time'] += end_time - self.telemetry['last_standing']
            if self.telemetry['last_sitting'] is not None:
                self.telemetry['sitting_time'] += end_time - self.telemetry['last_sitting']
            if self.telemetry['last_absence'] is not None:
                self.telemetry['absence_time'] += end_time - self.telemetry['last_absence']
            if self.telemetry['last_pitch_on'] is not None:
                self.telemetry['pitch_on_time'] += end_time - self.telemetry['last_pitch_on']
            if self.telemetry['last_yaw_on'] is not None:
                self.telemetry['yaw_on_time'] += end_time - self.telemetry['last_yaw_on']
            if self.telemetry['last_roll_on'] is not None:
                self.telemetry['roll_on_time'] += end_time - self.telemetry['last_roll_on']
            if self.telemetry['last_em_on'] is not None:
                self.telemetry['em_on_time'] += end_time - self.telemetry['last_em_on']
            if self.telemetry['last_ed_on'] is not None:
                self.telemetry['ed_on_time'] += end_time - self.telemetry['last_ed_on']
            if self.telemetry['last_bad_posture_time'] is not None:
                self.telemetry['bad_posture_time'] += end_time - self.telemetry['last_bad_posture_time']

            # Flush do buffer de leituras antes de finalizar
            self._flush_readings_buffer()

            summary = self._build_session_summary(end_time)
            user_id = database.get_user_id(self.current_user)
            if user_id is not None:
                # Atualizar sessão existente ou criar nova
                if self.current_session_id is not None:
                    session_id = self.current_session_id
                else:
                    session_id = database.create_session(user_id, summary)
                
                database.insert_report(user_id, session_id, summary)
                logger.info(f"Relatorio de telemetria salvo no banco para usuario {self.current_user} (sessao {session_id}).")
                
                # Resetar session_id
                self.current_session_id = None
            else:
                logger.warning(f"Usuario {self.current_user} nao encontrado ao salvar telemetria.")

            return summary

        except Exception as e:
            logger.error(f"Erro ao finalizar telemetria: {e}")
            return None
