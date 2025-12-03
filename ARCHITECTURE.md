# Arquitetura do Sistema

## 📐 Visão Geral

O Sistema de Análise de Postura é uma aplicação web em tempo real que utiliza visão computacional para monitorar e analisar a postura corporal.

## 🏗️ Componentes Principais

### 1. Backend (Python/Flask)

#### `app.py` - Servidor Principal
- **Framework**: Flask + Flask-SocketIO
- **Responsabilidades**:
  - Servir interface web
  - Gerenciar conexões WebSocket
  - Endpoints REST API
  - Coordenar análise e calibração
- **Principais Rotas**:
  - `GET /` - Interface principal
  - `GET /video_feed` - Stream de vídeo
  - `GET /api/users` - Lista usuários
  - `GET /api/reports/<username>` - Relatórios
  - `DELETE /api/user/<username>` - Remover usuário

#### `posture_analyzer.py` - Motor de Análise
- **Classe Principal**: `PostureAnalyzer`
- **Responsabilidades**:
  - Gerenciar câmera RealSense
  - Processar frames com MediaPipe
  - Executar calibração de usuários
  - Realizar análise em tempo real
  - Coletar telemetria
- **Threads**:
  - `_calibration_loop()` - Loop de calibração
  - `_analysis_loop()` - Loop de análise
  - `generate_frames()` - Stream de vídeo

#### `posture_detector.py` - Algoritmos de Detecção
- **Classes**:
  - `PostureDetector` - Detector principal
  - `EMA` - Filtro de média móvel exponencial
  - `MedianFilter` - Filtro de mediana
  - `Latch` - Sistema de histerese temporal
- **Funcionalidades**:
  - Cálculo de ângulos (pitch, yaw, roll)
  - Detecção de posição (em pé/sentado)
  - Sistema de alertas com limiares
  - Filtragem de sinais

#### `database.py` - Camada de Dados
- **Banco**: SQLite
- **Tabelas**:
  - `users` - Dados de calibração
  - `sessions` - Sessões de análise
  - `reports` - Relatórios de telemetria
  - `posture_readings` - Leituras frame-a-frame
  - `metrics` - Métricas agregadas
- **Operações**:
  - CRUD de usuários
  - Inserção em lote de leituras
  - Consultas de relatórios

#### `utils.py` - Utilitários
- Conversão de tipos NumPy para JSON
- Funções auxiliares compartilhadas

### 2. Frontend (HTML/JavaScript)

#### `templates/main.html` - Interface Web
- **Tecnologias**:
  - HTML5 + CSS3
  - JavaScript (Vanilla)
  - Socket.IO Client
  - Chart.js (gráficos)
- **Páginas**:
  - Criar Usuário (calibração)
  - Iniciar Análise (monitoramento)
  - Apagar Usuário (gerenciamento)
  - Verificar Leituras (relatórios)
- **Visualizações**:
  - Visão Operador (simplificada)
  - Visão Gestor (detalhada)

## 🔄 Fluxo de Dados

### Calibração
```
Usuário → Interface Web → WebSocket → app.py
                                        ↓
                              posture_analyzer.py
                                        ↓
                              RealSense Camera → MediaPipe
                                        ↓
                              posture_detector.py (cálculos)
                                        ↓
                              database.py (salvar)
                                        ↓
                              WebSocket → Interface Web
```

### Análise em Tempo Real
```
Loop contínuo (30 FPS):
RealSense Camera → MediaPipe Pose → posture_detector.py
                                            ↓
                                    Cálculo de métricas
                                            ↓
                                    Sistema de alertas
                                            ↓
                                    database.py (buffer)
                                            ↓
                                    WebSocket → Interface Web
```

## 🎯 Algoritmos Principais

### Detecção de Postura

1. **Captura de Landmarks**
   - MediaPipe detecta 33 pontos do corpo
   - Foco em: ombros, quadris, cabeça, olhos

2. **Cálculo de Eixos Corporais**
   ```python
   x_body = normalize(RS - LS)  # Eixo lateral (ombros)
   z_body = normalize(cross(x_body, up))  # Eixo frontal
   y_body = normalize(cross(z_body, x_body))  # Eixo vertical
   ```

3. **Cálculo de Ângulos**
   - **Pitch**: Inclinação frontal (arctan2)
   - **Yaw**: Rotação lateral (arctan2)
   - **Roll**: Inclinação lateral (arcsin)

4. **Filtragem de Sinais**
   - EMA para suavização
   - Filtro de mediana para ruído
   - Latch para estabilidade de alertas

5. **Detecção de Posição**
   - Análise de queda dos ombros
   - Distância do peito (profundidade Z)
   - Sistema de pontuação com latch

### Sistema de Alertas

```python
Latch(
    on_thr=10.0,        # Limiar de ativação
    off_ratio=0.75,     # Razão de desativação
    min_frames_on=10    # Frames mínimos para confirmar
)
```

- Evita alertas falsos (ruído)
- Requer persistência temporal
- Histerese para estabilidade

## 🗄️ Modelo de Dados

### Calibração do Usuário
```json
{
  "timestamp": 1234567890,
  "up": [0.0, -1.0, 0.0],
  "baseline": {
    "mu_pitch": 5.2,
    "mu_yaw": 0.1,
    "mu_roll": -1.3,
    "trunk_pitch": 2.1,
    "trunk_roll": 0.5,
    "ybar0": 0.45,
    "W0": 0.38,
    "z_chest0": 0.52
  },
  "fps": 30
}
```

### Leitura de Postura
```json
{
  "timestamp": 1234567890.123,
  "frame_number": 1500,
  "pitch_raw": 12.5,
  "pitch_filtered": 11.8,
  "pitch_diff": 6.6,
  "standing": true,
  "pitch_on": true,
  "events": {...}
}
```

## 🔐 Segurança

- Dados armazenados localmente (SQLite)
- Sem transmissão externa de vídeo
- WebSocket com CORS configurável
- Sem autenticação (sistema local)

## ⚡ Performance

- **FPS**: ~30 frames/segundo
- **Latência**: <50ms (WebSocket)
- **Batch Insert**: 30 leituras por vez
- **Memória**: ~500MB (com câmera ativa)

## 🔧 Configurações

### Limiares Ajustáveis
- `posture_detector.py`: Limiares de alertas
- `posture_analyzer.py`: Parâmetros de calibração
- `app.py`: Porta e host do servidor

### Otimizações Possíveis
- Reduzir resolução da câmera
- Ajustar FPS de captura
- Modificar tamanho do buffer
- Alterar complexidade do modelo MediaPipe

## 📊 Métricas Coletadas

### Por Frame
- Ângulos brutos e filtrados
- Posição (em pé/sentado)
- Estado de cada alerta
- Timestamp preciso

### Por Sessão
- Duração total
- Tempo em cada posição
- Total de alertas por tipo
- Estatísticas (média, min, max)
- Percentual de má postura

## 🚀 Escalabilidade

### Limitações Atuais
- Single-user (uma câmera)
- Processamento local
- Banco SQLite (não distribuído)

### Possíveis Melhorias
- Multi-câmera (múltiplos usuários)
- Processamento em GPU
- Banco PostgreSQL
- API REST completa
- Autenticação de usuários
- Dashboard administrativo

## 📝 Notas Técnicas

### Coordenadas 3D
- Sistema RealSense: X (lateral), Y (vertical), Z (profundidade)
- Origem: Centro da câmera
- Unidades: Metros

### MediaPipe Pose
- Modelo: BlazePose
- Landmarks: 33 pontos
- Confiança mínima: 0.5
- Segmentação: Habilitada

### WebSocket Events
- `connect` / `disconnect`
- `start_calibration` / `stop_calibration`
- `start_analysis` / `stop_analysis`
- `calibration_data` / `posture_data`
- `camera_status`

---

Para mais detalhes, consulte o código-fonte e comentários inline.
