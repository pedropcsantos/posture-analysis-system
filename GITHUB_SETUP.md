# Configuração do Repositório GitHub

## 📋 Checklist de Arquivos

Certifique-se de que os seguintes arquivos estão no diretório:

### Arquivos Essenciais ✅
- [x] `app.py` - Aplicação principal
- [x] `posture_analyzer.py` - Motor de análise
- [x] `posture_detector.py` - Algoritmos de detecção
- [x] `database.py` - Camada de dados
- [x] `utils.py` - Utilitários
- [x] `requirements.txt` - Dependências Python
- [x] `templates/main.html` - Interface web

### Documentação ✅
- [x] `README.md` - Documentação principal
- [x] `LICENSE` - Licença MIT
- [x] `QUICK_START.md` - Guia rápido
- [x] `ARCHITECTURE.md` - Arquitetura do sistema
- [x] `.gitignore` - Arquivos a ignorar
- [x] `.env.example` - Exemplo de configuração

## 🚀 Passos para Publicar no GitHub

### 1. Inicializar Repositório Git (se ainda não foi feito)
```bash
cd c:/Projetos/Dissertacao
git init
```

### 2. Adicionar Arquivos
```bash
# Adicionar todos os arquivos essenciais
git add app.py
git add posture_analyzer.py
git add posture_detector.py
git add database.py
git add utils.py
git add requirements.txt
git add templates/main.html
git add README.md
git add LICENSE
git add .gitignore
git add .env.example
git add QUICK_START.md
git add ARCHITECTURE.md
git add GITHUB_SETUP.md
```

### 3. Verificar o que será commitado
```bash
git status
```

**Importante**: Verifique se arquivos sensíveis (*.db, *.bag, perfis/, etc.) NÃO aparecem na lista. Se aparecerem, eles estão sendo ignorados corretamente pelo .gitignore.

### 4. Fazer o Primeiro Commit
```bash
git commit -m "Initial commit: Sistema de Análise de Postura em Tempo Real

- Implementação completa do sistema de análise postural
- Interface web com visualizações em tempo real
- Sistema de calibração personalizada
- Detecção automática de má postura
- Telemetria e relatórios detalhados
- Documentação completa em português"
```

### 5. Criar Repositório no GitHub

1. Acesse: https://github.com/new
2. **Repository name**: `posture-analysis-system`
3. **Description**: `Sistema de análise de postura em tempo real usando Intel RealSense e MediaPipe`
4. **Visibility**: Public (ou Private, se preferir)
5. **NÃO** marque "Initialize with README" (já temos um)
6. Clique em "Create repository"

### 6. Conectar ao Repositório Remoto
```bash
# Substitua 'santospedropc' pelo seu username do GitHub
git remote add origin https://github.com/santospedropc/posture-analysis-system.git

# Verificar se foi adicionado corretamente
git remote -v
```

### 7. Fazer Push para o GitHub
```bash
# Primeira vez (cria a branch main)
git branch -M main
git push -u origin main

# Próximas vezes (após novos commits)
git push
```

### 8. Verificar no GitHub
Acesse: https://github.com/santospedropc/posture-analysis-system

Você deve ver:
- ✅ Todos os arquivos listados
- ✅ README.md renderizado na página principal
- ✅ Licença MIT identificada
- ✅ Linguagem Python detectada

## 🏷️ Adicionar Topics (Recomendado)

No GitHub, clique em "Add topics" e adicione:
- `posture-analysis`
- `computer-vision`
- `realsense`
- `mediapipe`
- `flask`
- `real-time`
- `ergonomics`
- `python`
- `websocket`

## 📝 Editar Descrição do Repositório

No GitHub, adicione:
```
Sistema completo de análise de postura em tempo real utilizando câmera Intel RealSense e MediaPipe. Monitoramento ergonômico com alertas, telemetria e relatórios detalhados.
```

## 🌐 Configurar GitHub Pages (Opcional)

Se quiser hospedar a documentação:
1. Settings → Pages
2. Source: Deploy from a branch
3. Branch: main / docs (se criar pasta docs)

## 🔄 Workflow de Desenvolvimento

### Fazer Alterações
```bash
# 1. Editar arquivos
# 2. Ver o que mudou
git status
git diff

# 3. Adicionar mudanças
git add arquivo_modificado.py

# 4. Commit
git commit -m "Descrição clara da mudança"

# 5. Push
git push
```

### Criar Branches para Features
```bash
# Criar e mudar para nova branch
git checkout -b feature/nova-funcionalidade

# Fazer alterações e commits
git add .
git commit -m "Adiciona nova funcionalidade"

# Push da branch
git push -u origin feature/nova-funcionalidade

# No GitHub, criar Pull Request
```

## 📊 Adicionar Badge ao README (Opcional)

Adicione no topo do README.md:
```markdown
![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![RealSense](https://img.shields.io/badge/Intel-RealSense-blue.svg)
![MediaPipe](https://img.shields.io/badge/Google-MediaPipe-red.svg)
```

## 🐛 Solução de Problemas

### Erro: "remote origin already exists"
```bash
git remote remove origin
git remote add origin https://github.com/santospedropc/posture-analysis-system.git
```

### Erro: "failed to push some refs"
```bash
# Puxar mudanças primeiro
git pull origin main --rebase
git push
```

### Arquivo grande bloqueando push
```bash
# Remover do histórico
git rm --cached arquivo_grande.bag
git commit -m "Remove arquivo grande"
git push
```

### Esqueceu de adicionar algo ao .gitignore
```bash
# Adicionar ao .gitignore
echo "arquivo_sensivel.db" >> .gitignore

# Remover do git (mas manter no disco)
git rm --cached arquivo_sensivel.db

# Commit
git commit -m "Atualiza .gitignore"
git push
```

## ✅ Checklist Final

Antes de considerar o repositório pronto:

- [ ] README.md está completo e claro
- [ ] LICENSE está presente
- [ ] .gitignore está funcionando (sem arquivos sensíveis)
- [ ] requirements.txt está atualizado
- [ ] Código está comentado adequadamente
- [ ] Não há senhas ou dados sensíveis no código
- [ ] Documentação está em português (conforme solicitado)
- [ ] Exemplos de uso estão claros
- [ ] Instruções de instalação foram testadas

## 🎉 Próximos Passos

Após publicar:
1. Compartilhe o link do repositório
2. Considere adicionar:
   - GitHub Actions (CI/CD)
   - Issues templates
   - Pull request templates
   - CHANGELOG.md
   - Testes automatizados
3. Mantenha o repositório atualizado
4. Responda issues e pull requests

## 📧 Suporte

Se tiver problemas:
- GitHub Docs: https://docs.github.com
- Git Docs: https://git-scm.com/doc
- Email: santospedropc@gmail.com

---

**Boa sorte com seu repositório! 🚀**
