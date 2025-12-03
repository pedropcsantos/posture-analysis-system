# -*- coding: utf-8 -*-
"""
Módulo de Detecção de Postura
Contém classes para análise de postura corporal e filtros de sinal
"""

import numpy as np

# --------- Funções Geométricas ---------
def _norm(v, eps=1e-8):
    """Normaliza um vetor"""
    v = np.asarray(v, float)
    n = np.linalg.norm(v)
    return v / (n + eps)

def deg(x):
    """Converte radianos para graus"""
    return float(np.degrees(x))

def angular_diff(a, b):
    """Calcula a diferença angular mínima entre dois ângulos em graus."""
    diff = ((a - b + 180) % 360) - 180
    return abs(diff)

# --------- Classes de Filtros ---------
class EMA:
    """Filtro de Média Móvel Exponencial (Exponential Moving Average)"""
    def __init__(self, alpha=0.25):
        self.a = float(alpha)
        self.v = None
    
    def step(self, x):
        x = float(x)
        self.v = x if self.v is None else self.a*x + (1-self.a)*self.v
        return self.v

class MedianFilter:
    """Filtro de Mediana com janela deslizante"""
    def __init__(self, window_size=5):
        self.window = []
        self.size = window_size
    
    def step(self, x):
        self.window.append(float(x))
        if len(self.window) > self.size:
            self.window.pop(0)
        return np.median(self.window)

class Latch:
    """
    Latch com histerese temporal.
    Liga quando 'val' >= on_thr por 'min_frames_on' frames consecutivos.
    Desliga quando val <= off_thr.
    """
    def __init__(self, on_thr, off_ratio=0.75, min_frames_on=10):
        self.on_thr = float(on_thr)
        self.off_thr = float(on_thr) * float(off_ratio)
        self.n = int(min_frames_on)
        self.on = False
        self.c = 0
    
    def step(self, val, cond=True):
        if not cond:
            # Condição inválida -> desliga latch
            self.on = False
            self.c = 0
            return False
        
        if not self.on:
            if val >= self.on_thr:
                self.c += 1
            else:
                self.c = 0
            if self.c >= self.n:
                self.on = True
        else:
            if val <= self.off_thr:
                self.on = False
                self.c = 0
        
        return self.on

# --------- Detector de Postura ---------
class PostureDetector:
    """
    Detector de postura corporal que:
    - Calcula eixos do tronco com LS/RS + up_world
    - Analisa ângulos da cabeça (pitch, yaw, roll)
    - Detecta posição Em Pé / Sentado por sistema de pontos (3 pistas):
        1) Altura do tronco (span vertical ombro-peito)
        2) Queda dos ombros vs baseline, normalizado por largura
        3) Avanço do tronco (distância do peito)
    - Detecta eventos de má postura (cabeça, ombros)
    """
    
    def __init__(self, up_world, baseline, fps,
                 ema_alpha=0.25, 
                 yaw_gate_deg=10.0,
                 pitch_thr_deg=(10, 20),
                 yaw_thr_deg=10,
                 roll_thr_deg=5,
                 trunk_pitch_thr_deg=(5, 20),
                 trunk_roll_thr_deg=(5),
                 persist_frames=10, 
                 k_chest=0.40,
                 elev_mean_thr=0.03, 
                 elev_diff_thr=0.05):
        """
        Inicializa o detector de postura.
        
        Args:
            up_world: Vetor "para cima" no sistema de coordenadas mundial
            baseline: Dict com valores de referência (mu_pitch, mu_yaw, mu_roll, ybar0, W0, z_chest0, L_tronco0)
            fps: Taxa de frames por segundo
            ema_alpha: Coeficiente do filtro EMA
            yaw_gate_deg: Limiar de yaw para validação
            pitch_thr_deg: Tupla com limiares de pitch (leve, moderado, severo)
            yaw_thr_deg: Limiar de yaw para alerta
            roll_thr_deg: Limiar de roll para alerta
            persist_frames: Frames necessários para persistir alerta
            k_chest: Coeficiente para cálculo do ponto do peito
            elev_mean_thr: Limiar de elevação média dos ombros
            elev_diff_thr: Limiar de diferença de elevação dos ombros
        """
        self.up = _norm(up_world)
        self.xc = np.array([1, 0, 0])
        self.zc = np.array([0, 0, 1])
        self.k_chest = float(k_chest)

        # Baselines de calibração
        self.mu_pitch = float(baseline["mu_pitch"])
        self.mu_yaw = float(baseline["mu_yaw"])
        self.mu_roll = float(baseline["mu_roll"])
        self.mu_trunk_pitch = float(baseline.get("trunk_pitch", 0.0))
        self.mu_trunk_roll  = float(baseline.get("trunk_roll",  0.0))
        self.ybar0 = float(baseline["ybar0"])
        self.W0 = float(baseline["W0"])
        self.z_chest0 = float(baseline.get("z_chest0", 0.0))

        # Filtros para métricas angulares
        self.emaP = EMA(ema_alpha)
        self.medianY = MedianFilter(window_size=5)
        self.medianTP = MedianFilter(window_size=5)    # trunk_pitch
        self.emaTR    = EMA(ema_alpha)                 # trunk_roll
        self.emaR = EMA(ema_alpha)
        self.emaEM = EMA(ema_alpha)
        self.emaED = EMA(ema_alpha)

        # Thresholds e latches dos eventos angulares
        self.yaw_gate_deg = yaw_gate_deg
        self.pitch_thr = pitch_thr_deg
        self.lP = Latch(pitch_thr_deg[0], min_frames_on=persist_frames)
        self.lY = Latch(yaw_thr_deg, off_ratio=0.9, min_frames_on=persist_frames)
        self.lR = Latch(roll_thr_deg, off_ratio=0.9, min_frames_on=persist_frames)
        self.lEM = Latch(elev_mean_thr, off_ratio=0.9, min_frames_on=persist_frames)
        self.lED = Latch(elev_diff_thr, off_ratio=0.9, min_frames_on=persist_frames)

        self.trunk_pitch_thr = trunk_pitch_thr_deg
        self.trunk_roll_thr  = trunk_roll_thr_deg
        self.lTP = Latch(trunk_pitch_thr_deg[0], min_frames_on=persist_frames)
        self.lTR = Latch(trunk_roll_thr_deg,  min_frames_on=persist_frames)

        # Novo latch para extensão da cabeça (ângulos negativos = inclinação para trás)
        self.lPExt = Latch(pitch_thr_deg[0], min_frames_on=persist_frames)  # extensão cabeça

        # Filtros para detecção de posição (Em Pé/Sentado)
        self.emaDrop = EMA(ema_alpha)
        self.emaDz = EMA(ema_alpha)

        # Limiares para detecção de posição sentado/em pé
        self.LIMIAR_DROPW = 0.15  # Queda dos ombros (normalizado por largura)
        self.LIMIAR_DZ = 0.09     # Avanço do peito (metros)

        # Latch do "Sentado" - baseado em comparação booleana
        self.latch_sit = Latch(1.0, off_ratio=0.5, min_frames_on=max(15, int(0.8*fps)))

    def _is_sitting(self, dropW_s, dz_s):
        """Verifica se está sentado baseado em duas condições booleanas"""
        # Sentado se AMBAS as condições forem verdadeiras:
        # 1. Ombros caíram (dropW > limiar)
        # 2. Peito avançou (dz > limiar)
        return (dropW_s > self.LIMIAR_DROPW) and (dz_s > self.LIMIAR_DZ)

    def step(self, LS, RS, H, LH=None, RH=None, arms_up=False):
        """
        Processa um frame e retorna métricas de postura.
        
        Args:
            LS: Ponto 3D do ombro esquerdo
            RS: Ponto 3D do ombro direito
            H: Ponto 3D da cabeça
            arms_up: Se os braços estão levantados
            
        Returns:
            Dict com métricas de postura, eventos e features
        """
        # Calcular eixos do tronco
        x_body = _norm(RS - LS)
        z_body = _norm(np.cross(x_body, self.up))
        y_body = _norm(np.cross(z_body, x_body))

        # Centro dos ombros e largura
        S = 0.5 * (LS + RS)
        W = float(np.linalg.norm(RS - LS))
        W_eff = W if W > 1e-6 else (self.W0 if self.W0 else 0.35)

        # Peito sintético
        C = S - self.k_chest * y_body * W_eff

        # Vetor peito->cabeça e ângulos
        u = H - C
        if np.dot(u, z_body) < 0:
            z_body = -z_body
            y_body = _norm(np.cross(z_body, x_body))

        u_sag = _norm(u - np.dot(u, x_body) * x_body)
        ty, tz = np.dot(u_sag, y_body), np.dot(u_sag, z_body)
        pitch = deg(np.arctan2(tz, ty))
        yaw = deg(np.arctan2(np.dot(z_body, self.xc), np.dot(z_body, self.zc)))
        roll = deg(np.arcsin(np.clip(np.dot(x_body, self.up), -1, 1)))

        # Aplicar filtros
        P = self.emaP.step(pitch)
        Y = self.medianY.step(yaw)
        R = self.emaR.step(roll)

        # Elevação dos ombros
        ybar = 0.5 * (LS[1] + RS[1])
        em = (self.ybar0 - ybar) / W_eff 
        ed = (LS[1] - RS[1]) / W_eff

        EM = self.emaEM.step(em)
        ED = self.emaED.step(ed)

        # tronco

        TP = None; TR = None; Y_trunk = None
        if LH is not None and RH is not None:
            mid_shoulder = S
            mid_hip      = 0.5 * (LH + RH)
            trunk_vec    = _norm(mid_shoulder - mid_hip)
            # pitch/roll do tronco
            TP = self.medianTP.step(deg(np.arcsin(np.clip(trunk_vec[2], -1, 1))))
            TR = self.emaTR.step( deg(np.arcsin(np.clip(trunk_vec[0], -1, 1))) )

            # yaw do tronco (projeção horizontal)
            v_h = trunk_vec - np.dot(trunk_vec, self.up)*self.up
            n = np.linalg.norm(v_h)
            if n > 1e-8:
                v_h = v_h / n
                Y_trunk = deg(np.arctan2(np.dot(v_h, self.xc), np.dot(v_h, self.zc))) #testar, mas provavelmente nao vai ser usado

        # Detecção de posição: Em Pé / Sentado
        dropW = (ybar - self.ybar0) / W_eff
        dropW_s = self.emaDrop.step(dropW)

        dz = (C[2] - self.z_chest0) if self.z_chest0 > 0 else 0.0
        dz_s = self.emaDz.step(dz)

        # Verificar se está sentado (comparação booleana simples)
        is_sitting = self._is_sitting(dropW_s, dz_s)
        # Usar latch para estabilizar a detecção (1.0 se sentado, 0.0 se em pé)
        sit_on = self.latch_sit.step(1.0 if is_sitting else 0.0)
        standing = not sit_on

        # Eventos de má postura - só quando em pé
        if standing:
            pex = abs(P - self.mu_pitch)
            level = 0
            if pex >= self.pitch_thr[1]:
                level = 2
            elif pex >= self.pitch_thr[0]:
                level = 1

            # tronco
            yaw_gate_ok = angular_diff(Y, self.mu_yaw) < self.yaw_gate_deg
            tp_level = 0; tr_level = 0
            evTP = False; evTR = False
            if TP is not None:
                dp = angular_diff(TP, self.mu_trunk_pitch)
                if dp >= self.trunk_pitch_thr[1]: tp_level = 2
                elif dp >= self.trunk_pitch_thr[0]: tp_level = 1
                evTP = self.lTP.step(dp,  cond=yaw_gate_ok and not arms_up)
            if TR is not None:
                dr = angular_diff(TR, self.mu_trunk_roll)
                # trunk_roll_thr agora é um único valor (1 nível)
                if dr >= self.trunk_roll_thr: tr_level = 1
                evTR = self.lTR.step(dr, cond=not arms_up)

            pitch_gate_ok = pex <= self.pitch_thr[0]
            
            evP = self.lP.step(pex, cond=yaw_gate_ok and not arms_up)
            evY = self.lY.step(angular_diff(Y, self.mu_yaw), cond=not arms_up)
            evR = self.lR.step(abs(R - self.mu_roll), cond= not arms_up)
            evEM = self.lEM.step(EM, cond=yaw_gate_ok and not arms_up)
            evED = self.lED.step(abs(ED), cond=pitch_gate_ok and yaw_gate_ok and not arms_up)

            # Evento de extensão da cabeça (ângulos negativos = inclinação para trás)
            evPExt = self.lPExt.step(-P, cond=yaw_gate_ok and not arms_up)  # extensão cabeça (P negativo)
        else:
            # Quando sentado, desativar eventos
            level = 0
            tp_level = 0
            tr_level = 0
            yaw_gate_ok = False
            pitch_gate_ok = False
            evP = evY = evR = evEM = evED = evTP = evTR = evPExt = False

        return dict(
            # Valores filtrados
            pitch=P, yaw=Y, roll=R,
            trunk_pitch=TP, trunk_roll=TR,
            em=EM, ed=ED, W=W*100,
            # Valores brutos (antes dos filtros)
            raw_values=dict(
                pitch=pitch,
                yaw=yaw,
                roll=roll,
                trunk_pitch=TP,  # já vem do MedianFilter
                trunk_roll=TR,   # já vem do EMA
                em=em,
                ed=ed
            ),
            C=C, S=S,H=H,
            x_body=x_body, y_body=y_body, z_body=z_body,
            standing=standing,
            gate_features=dict(
                dropW=dropW_s, dz=dz_s,
                is_sitting=is_sitting
            ),
            events=dict(
                pitch_on=evP, pitch_level=level,
                yaw_on=evY,
                roll_on=evR,
                trunk_pitch_on=evTP, trunk_pitch_level=tp_level,
                trunk_roll_on=evTR,
                head_extension_on=evPExt,  # extensão cabeça
                em_on=evEM, ed_on=evED,
                yaw_gate_ok=yaw_gate_ok, arms_block=arms_up
            )
        )
