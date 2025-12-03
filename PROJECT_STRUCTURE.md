# Estrutura do Projeto

## 📁 Organização de Arquivos

```
posture-analysis-system/
│
├── 📄 app.py                          # Servidor Flask principal (API + WebSocket)
├── 📄 posture_analyzer.py             # Motor de análise e gerenciamento da câmera
├── 📄 posture_detector.py             # Algoritmos de detecção e filtros
├── 📄 database.py                     # Camada de acesso ao banco de dados SQLite
├── 📄 utils.py                        # Funções utilitárias
├── 📄 requirements.txt                # Dependências Python
│
├── 📁 templates/                      # Templates HTML
│   └── 📄 main.html                   # Interface web completa
│
├── 📄 README.md                       # Documentação principal (VOCÊ ESTÁ AQUI)
├── 📄 LICENSE                         # Licença MIT
├── 📄 .gitignore                      # Arquivos a serem ignorados pelo Git
├── 📄 .env.example                    # Exemplo de variáveis de ambiente
├── 📄 QUICK_START.md                  # Guia rápido de inicialização
├── 📄 ARCHITECTURE.md                 # Documentação da arquitetura
├── 📄 GITHUB_SETUP.md                 # Instruções para publicar no GitHub
└── 📄 PROJECT_STRUCTURE.md            # Este arquivo
│
├── 🗄️ posture_system.db               # Banco de dados (gerado automaticamente)
│                                      # ⚠️ NÃO incluir no Git (.gitignore)
│
└── 📁 (outros diretórios ignorados)
    ├── perfis/                        # Imagens de perfil dos usuários
    ├── reports/                       # Relatórios CSV gerados
    ├── debug_output/                  # Saídas de debug
    └── backup/                        # Backups
```

## 📊 Fluxo de Arquivos

### Durante a Execução

```
┌─────────────────────────────────────────────────────────────┐
│                         app.py                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Flask Server (HTTP + WebSocket)                     │  │
│  │  - Serve templates/main.html                         │  │
│  │  - Gerencia rotas REST API                           │  │
│  │  - Coordena WebSocket events                         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑
┌─────────────────────────────────────────────────────────────┐
│                   posture_analyzer.py                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  PostureAnalyzer Class                               │  │
│  │  - Gerencia câmera RealSense                         │  │
│  │  - Processa frames com MediaPipe                     │  │
│  │  - Executa loops de calibração/análise              │  │
│  │  - Coleta telemetria                                 │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑
┌─────────────────────────────────────────────────────────────┐
│                   posture_detector.py                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  PostureDetector Class                               │  │
│  │  - Calcula ângulos e métricas                        │  │
│  │  - Aplica filtros (EMA, Median)                      │  │
│  │  - Detecta posição (em pé/sentado)                   │  │
│  │  - Sistema de alertas com Latch                      │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑
┌─────────────────────────────────────────────────────────────┐
│                      database.py                            │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLite Database Layer                               │  │
│  │  - CRUD de usuários                                  │  │
│  │  - Gerenciamento de sessões                          │  │
│  │  - Armazenamento de leituras                         │  │
│  │  - Geração de relatórios                             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓ ↑
┌─────────────────────────────────────────────────────────────┐
│                   posture_system.db                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  SQLite Database File                                │  │
│  │  - users (calibração)                                │  │
│  │  - sessions (sessões)                                │  │
│  │  - reports (relatórios)                              │  │
│  │  - posture_readings (leituras frame-a-frame)         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## 🔄 Ciclo de Vida dos Dados

### 1. Calibração
```
Usuário → Interface Web → WebSocket → app.py
                                        ↓
                              posture_analyzer.py
                                        ↓
                        RealSense Camera + MediaPipe
                                        ↓
                              posture_detector.py
                                        ↓
                              database.py → users table
```

### 2. Análise em Tempo Real
```
Loop (30 FPS):
RealSense → MediaPipe → posture_detector → Buffer (30 frames)
                                              ↓
                                    database.py → posture_readings
                                              ↓
                                    WebSocket → Interface Web
```

### 3. Finalização de Sessão
```
Stop Analysis → posture_analyzer.finalize_telemetry()
                        ↓
                Flush buffer → database.py
                        ↓
                Calcular estatísticas
                        ↓
                Salvar em reports table
```

## 📦 Dependências entre Módulos

```
app.py
  ├── imports posture_analyzer
  ├── imports database
  └── imports utils

posture_analyzer.py
  ├── imports posture_detector
  ├── imports database
  └── imports utils

posture_detector.py
  └── (sem dependências internas)

database.py
  └── (sem dependências internas)

utils.py
  └── (sem dependências internas)
```

## 🎯 Pontos de Entrada

### Para Usuário Final
```
python app.py → http://localhost:5000
```

### Para Desenvolvimento
```python
# Testar detector isoladamente
from posture_detector import PostureDetector
detector = PostureDetector(up_world, baseline, fps=30)

# Testar banco de dados
from database import initialize_database, create_user
initialize_database()
create_user("teste", calibration_data)

# Testar análise
from posture_analyzer import PostureAnalyzer
analyzer = PostureAnalyzer()
```

## 📝 Arquivos de Configuração

### requirements.txt
```
flask==2.3.3
flask-socketio==5.3.6
opencv-python==4.8.1.78
mediapipe==0.10.7
pyrealsense2==2.54.1.5217
numpy==1.24.3
python-socketio==5.9.0
eventlet==0.33.3
```

### .env.example (opcional)
```
FLASK_PORT=5000
DATABASE_PATH=posture_system.db
CAMERA_WIDTH=640
CAMERA_HEIGHT=480
```

## 🚫 Arquivos Ignorados (.gitignore)

### Dados Sensíveis
- `*.db` - Bancos de dados
- `perfis/` - Fotos de usuários
- `reports/` - Relatórios gerados

### Arquivos Grandes
- `*.bag` - Gravações RealSense
- `*.pt` - Modelos YOLO
- `*.task` - Modelos MediaPipe

### Temporários
- `__pycache__/`
- `*.pyc`
- `venv/`
- `.env`

## 📊 Tamanho dos Arquivos (Aproximado)

```
app.py                 ~15 KB
posture_analyzer.py    ~35 KB
posture_detector.py    ~12 KB
database.py            ~20 KB
utils.py               ~2 KB
templates/main.html    ~80 KB
requirements.txt       ~1 KB
README.md              ~15 KB
Total (código)         ~180 KB

posture_system.db      Varia (cresce com uso)
                       ~100 KB vazio
                       ~10 MB após várias sessões
```

## 🔧 Modificações Comuns

### Alterar Porta do Servidor
📄 `app.py` (última linha):
```python
socketio.run(app, host='0.0.0.0', port=5000, debug=False)
```

### Ajustar Limiares de Alerta
📄 `posture_detector.py` (classe PostureDetector):
```python
def __init__(self, ..., pitch_thr_deg=(10, 20), ...):
```

### Modificar Resolução da Câmera
📄 `posture_analyzer.py` (método start_analysis):
```python
config.enable_stream(rs.stream.color, 640, 480, rs.format.bgr8, 30)
```

### Alterar Tamanho do Buffer
📄 `posture_analyzer.py` (classe PostureAnalyzer):
```python
self.readings_buffer_size = 30
```

## 📚 Documentação Adicional

- **README.md** - Visão geral e instalação
- **QUICK_START.md** - Início rápido (5 minutos)
- **ARCHITECTURE.md** - Arquitetura detalhada
- **GITHUB_SETUP.md** - Publicação no GitHub
- **PROJECT_STRUCTURE.md** - Este arquivo

## 🆘 Onde Encontrar o Quê

| Preciso de...                    | Arquivo                  |
|----------------------------------|--------------------------|
| Iniciar o servidor               | `app.py`                 |
| Modificar interface              | `templates/main.html`    |
| Ajustar detecção                 | `posture_detector.py`    |
| Alterar calibração               | `posture_analyzer.py`    |
| Modificar banco de dados         | `database.py`            |
| Adicionar dependência            | `requirements.txt`       |
| Documentação de uso              | `README.md`              |
| Entender arquitetura             | `ARCHITECTURE.md`        |
| Guia rápido                      | `QUICK_START.md`         |

---

**Dica**: Use `Ctrl+F` para buscar rapidamente neste documento!
