# Sistema de Análise de Postura em Tempo Real

Sistema completo para monitoramento e análise postural em tempo real utilizando câmera Intel RealSense e MediaPipe.

## 📋 Descrição

Este sistema oferece uma solução completa para análise de postura corporal em tempo real, ideal para ambientes de trabalho, fisioterapia, ergonomia e pesquisa. Utiliza visão computacional avançada para detectar e alertar sobre má postura, fornecendo telemetria detalhada e relatórios personalizados.

## ✨ Funcionalidades

- **Calibração Personalizada**: Sistema de calibração individual para cada usuário
- **Monitoramento em Tempo Real**: Análise contínua da postura com feedback instantâneo
- **Detecção Inteligente**: Identifica automaticamente posição (em pé/sentado) e má postura
- **Alertas Configuráveis**: Sistema de alertas para:
  - Inclinação frontal da cabeça
  - Rotação lateral dos ombros
  - Inclinação lateral dos ombros
  - Inclinação do tronco
  - Elevação e assimetria dos ombros
- **Telemetria Avançada**: Coleta e armazenamento de métricas detalhadas
- **Relatórios Visuais**: Gráficos e estatísticas de sessões de análise
- **Interface Web Intuitiva**: Dashboard completo com visualizações em tempo real
- **Múltiplas Visualizações**: Visão operador (simplificada) e visão gestor (detalhada)

## 🔧 Requisitos

### Hardware
- **Câmera Intel RealSense** (testado com D435/D455)
- **Porta USB 3.0** (obrigatório para funcionamento adequado da câmera)
- Processador: Intel Core i5 ou superior (recomendado i7)
- RAM: 8GB mínimo (16GB recomendado)
- Sistema Operacional: Windows 10/11, Linux (Ubuntu 20.04+)

### Software
- Python 3.8 ou superior
- Drivers Intel RealSense SDK 2.0
- Navegador web moderno (Chrome, Firefox, Edge)

## 📦 Instalação

### 1. Clonar o Repositório
```bash
git clone https://github.com/santospedropc/posture-analysis-system.git
cd posture-analysis-system
```

### 2. Criar Ambiente Virtual (Recomendado)
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Instalar Dependências
```bash
pip install -r requirements.txt
```

### 4. Instalar Intel RealSense SDK

#### Windows
1. Baixe o instalador do [Intel RealSense SDK](https://github.com/IntelRealSense/librealsense/releases)
2. Execute o instalador e siga as instruções
3. Conecte a câmera RealSense em uma **porta USB 3.0**

#### Linux (Ubuntu)
```bash
sudo apt-key adv --keyserver keyserver.ubuntu.com --recv-key F6E65AC044F831AC80A06380C8B3A55A6F3EFCDE
sudo add-apt-repository "deb https://librealsense.intel.com/Debian/apt-repo $(lsb_release -cs) main"
sudo apt-get update
sudo apt-get install librealsense2-dkms librealsense2-utils librealsense2-dev
```

### 5. Verificar Instalação da Câmera
```bash
# Deve listar a câmera conectada
realsense-viewer
```

## 🚀 Uso

### Iniciar o Servidor
```bash
python app.py
```

O servidor iniciará em `http://localhost:5000`

### Fluxo de Trabalho

#### 1. Criar Usuário (Calibração)
1. Acesse a interface web
2. Clique em "Criar Usuário"
3. Digite o nome do usuário
4. Clique em "Visualizar Câmera" para verificar posicionamento
5. Posicione-se de frente para a câmera em posição neutra
6. Clique em "Iniciar Calibração"
7. Aguarde a detecção e clique em "Começar Coleta"
8. Mantenha-se imóvel durante a coleta (~30 segundos)
9. Clique em "Salvar Calibração"

#### 2. Iniciar Análise
1. Clique em "Iniciar Análise"
2. Selecione o usuário calibrado
3. Clique em "Iniciar Análise"
4. Escolha entre "Visão Operador" ou "Visão Gestor"
5. Monitore a postura em tempo real

#### 3. Visualizar Relatórios
1. Clique em "Verificar Últimas Leituras"
2. Selecione o usuário
3. Escolha a sessão desejada
4. Visualize gráficos e estatísticas detalhadas

## 📁 Estrutura do Projeto

```
posture-analysis-system/
├── app.py                      # Aplicação Flask principal
├── posture_analyzer.py         # Motor de análise de postura
├── posture_detector.py         # Algoritmos de detecção
├── database.py                 # Camada de acesso ao banco de dados
├── utils.py                    # Funções utilitárias
├── requirements.txt            # Dependências Python
├── templates/
│   └── main.html              # Interface web
├── posture_system.db          # Banco de dados SQLite (gerado automaticamente)
└── README.md                  # Este arquivo
```

## 🗄️ Banco de Dados

O sistema utiliza SQLite para armazenar:
- **users**: Dados de calibração dos usuários
- **sessions**: Sessões de análise
- **reports**: Relatórios de telemetria
- **posture_readings**: Leituras detalhadas de postura (frame a frame)

O banco de dados é criado automaticamente na primeira execução.

## ⚙️ Configuração

### Portas
- Servidor web: `5000` (padrão)
- WebSocket: mesma porta do servidor

Para alterar a porta, edite `app.py`:
```python
socketio.run(app, host='0.0.0.0', port=5000, debug=False)
```

### Parâmetros de Detecção

Os limiares de detecção podem ser ajustados em `posture_detector.py`:
```python
PostureDetector(
    pitch_thr_deg=(10, 20),      # Limiar de inclinação da cabeça
    yaw_thr_deg=10,              # Limiar de rotação
    roll_thr_deg=5,              # Limiar de inclinação lateral
    trunk_pitch_thr_deg=(5, 20), # Limiar de inclinação do tronco
    trunk_roll_thr_deg=5,        # Limiar de inclinação lateral do tronco
    elev_mean_thr=0.03,          # Limiar de elevação dos ombros
    elev_diff_thr=0.05           # Limiar de assimetria dos ombros
)
```

## 🔍 Solução de Problemas

### Câmera não detectada
- Verifique se a câmera está conectada em uma **porta USB 3.0**
- Confirme que os drivers Intel RealSense estão instalados
- Execute `realsense-viewer` para testar a câmera
- Reinicie o computador após instalar os drivers

### Erro de permissão (Linux)
```bash
sudo usermod -a -G video $USER
# Faça logout e login novamente
```

### Baixo desempenho
- Feche outros aplicativos que usam a câmera
- Reduza a resolução da câmera (edite `posture_analyzer.py`)
- Verifique se está usando USB 3.0 (não 2.0)

### Erro ao importar pyrealsense2
```bash
pip uninstall pyrealsense2
pip install pyrealsense2
```

## 📊 Métricas Coletadas

O sistema coleta as seguintes métricas:
- **Ângulos da cabeça**: pitch (frontal), yaw (rotação), roll (lateral)
- **Ângulos do tronco**: pitch (frontal), roll (lateral)
- **Ombros**: elevação, assimetria, largura
- **Tempo**: em pé, sentado, ausente, má postura
- **Alertas**: contagem por tipo de desvio postural

## 🤝 Contribuindo

Contribuições são bem-vindas! Por favor:
1. Faça um fork do projeto
2. Crie uma branch para sua feature (`git checkout -b feature/NovaFuncionalidade`)
3. Commit suas mudanças (`git commit -m 'Adiciona nova funcionalidade'`)
4. Push para a branch (`git push origin feature/NovaFuncionalidade`)
5. Abra um Pull Request

## 📝 Licença

Este projeto está licenciado sob a Licença MIT - veja o arquivo [LICENSE](LICENSE) para detalhes.

## 👤 Autor

**Pedro Paulo Campos Santos**
- Email: santospedropc@gmail.com
- GitHub: [@santospedropc](https://github.com/santospedropc)

## 🙏 Agradecimentos

- Intel RealSense SDK
- MediaPipe (Google)
- Flask e Flask-SocketIO
- Comunidade open-source

## 📚 Referências

- [Intel RealSense Documentation](https://dev.intelrealsense.com/)
- [MediaPipe Pose](https://google.github.io/mediapipe/solutions/pose.html)
- [Flask Documentation](https://flask.palletsprojects.com/)

---

**Nota**: Este sistema é destinado para fins de pesquisa e monitoramento ergonômico. Não substitui avaliação médica profissional.
