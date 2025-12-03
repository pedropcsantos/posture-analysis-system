# Guia Rápido de Inicialização

## 🚀 Início Rápido (5 minutos)

### Pré-requisitos
- ✅ Python 3.8+ instalado
- ✅ Câmera Intel RealSense conectada em **USB 3.0**
- ✅ Drivers Intel RealSense SDK instalados

### Passos

#### 1. Clone e Configure
```bash
git clone https://github.com/santospedropc/posture-analysis-system.git
cd posture-analysis-system
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate

pip install -r requirements.txt
```

#### 2. Verifique a Câmera
```bash
# Deve mostrar a câmera conectada
realsense-viewer
```

#### 3. Inicie o Sistema
```bash
python app.py
```

#### 4. Acesse a Interface
Abra o navegador em: **http://localhost:5000**

### Primeiro Uso

1. **Criar Usuário**
   - Digite seu nome
   - Clique em "Visualizar Câmera"
   - Posicione-se de frente para a câmera
   - Clique em "Iniciar Calibração"
   - Aguarde e clique em "Começar Coleta"
   - Mantenha-se imóvel por ~30 segundos
   - Clique em "Salvar Calibração"

2. **Iniciar Análise**
   - Selecione seu usuário
   - Clique em "Iniciar Análise"
   - Monitore sua postura em tempo real!

## ⚠️ Problemas Comuns

### Câmera não detectada
```bash
# Verifique se está em USB 3.0 (porta azul)
# Reinstale os drivers RealSense
```

### Erro de importação
```bash
pip install --upgrade pip
pip install -r requirements.txt --force-reinstall
```

### Porta 5000 em uso
Edite `app.py` linha final:
```python
socketio.run(app, host='0.0.0.0', port=5001, debug=False)
```

## 📚 Documentação Completa
Veja [README.md](README.md) para informações detalhadas.

## 🆘 Suporte
- Email: santospedropc@gmail.com
- Issues: https://github.com/santospedropc/posture-analysis-system/issues
