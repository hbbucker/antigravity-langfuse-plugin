# Antigravity & StartupOS Langfuse Observability Plugin 🚀

Plugin oficial de telemetria, rastreamento de custos por **Feature** e observabilidade de **Subagentes** para **Antigravity CLI** e **StartupOS**.

Projetado com arquitetura 100% agnóstica de sistema operacional, funcionando de forma idêntica e sem atritos no **Windows** (PowerShell, CMD) e **Linux** (Bash, Zsh).

---

## ✨ Principais Recursos

- 📊 **Rastreamento por Feature**: Detecta automaticamente features do StartupOS a partir de `.specs/features/<slug>/` e nomeia os traces canonicamente como `Feature: <slug>`.
- 🌳 **Hierarquia Completa de Subagentes**: Captura invocações de subagentes (como `Tasks Planner`, `CTO - Maker`, etc.), aninhando-os como spans do tipo `AGENT` dentro da trace da feature correspondente, agregando tokens e custos totais.
- 💰 **Cálculo de Custos Multi-Modelo**: Mapeamento preciso de modelos (Gemini 2.5 Flash, Gemini 2.5 Pro, Claude 3.5 Sonnet, etc.) com tokens de entrada e saída.
- ⚡ **Dual-Mode Flexível (Remoto vs Local)**:
  - **Modo Remoto (Cloud ou Servidor Corporativo)**: Conecte diretamente ao `https://cloud.langfuse.com` ou ao cluster da empresa sem rodar nenhum container na sua máquina.
  - **Modo Local (Docker)**: Suba o stack completo do Langfuse em segundos via Docker Compose.
- 🛡️ **Fail-Safe Não Bloqueante**: Se o Langfuse estiver offline ou indisponível, o tracer finaliza silenciosamente (`{}` e exit code 0), garantindo que o Antigravity CLI nunca trave ou interrompa seu trabalho.
- 🪟 **Multiplataforma (Windows & Linux)**:
  - Normaliza automaticamente separadores de caminhos (`\` vs `/`).
  - Execução via `node scripts/run_tracer.mjs`, compatível com o mecanismo nativo de hooks do Antigravity CLI.

---

## 📦 Estrutura do Pacote

```text
antigravity-langfuse-plugin/
├── plugin.json                 # Manifesto do plugin Antigravity CLI
├── hooks.json                  # Hook de ciclo de vida Stop -> run_tracer.mjs
├── package.json                # Metadados NPM e scripts de automação
├── docker-compose.yml          # Stack completo pronto para uso local
├── scripts/
│   ├── run_tracer.mjs          # Launcher universal multiplataforma (Node.js)
│   ├── langfuse_tracer.py      # Core de telemetria, detecção de contexto e sync
│   ├── setup.mjs               # Assistente interativo de configuração
│   └── provision_dashboard.py  # Verificador de integridade e telemetria
└── README.md                   # Esta documentação
```

---

## 🚀 Instalação Rápida

### Pré-requisitos
- **Node.js** v18+ (já presente no Antigravity CLI).
- **Python** 3.9+ com a biblioteca `langfuse`:
  ```bash
  # Windows ou Linux:
  pip install "langfuse>=2.50.0"
  ```

---

### Opção 1: Via Antigravity CLI (Recomendado)

```bash
# A partir do repositório Git:
agy plugin install https://github.com/hbbucker/antigravity-langfuse-plugin.git

# Ou a partir de diretório local:
agy plugin install ./caminho/para/antigravity-langfuse-plugin
```

---

### Opção 2: Via StartupOS

```bash
npx create-startupos telemetry:setup
# ou se já estiver no projeto:
npm run telemetry:setup
```

---

## ⚙️ Assistente de Configuração (`setup.mjs`)

O assistente interativo guia você na escolha entre o **Modo Remoto (Cloud)** ou **Modo Local (Docker)**:

```bash
# Executar assistente interativo:
node scripts/setup.mjs

# Ou via npm:
npm run setup
```

### 1. Configurando para Langfuse Cloud / Remoto
No assistente, selecione a opção **1 (Langfuse Remoto / Cloud)**:
1. Informe a URL: `https://cloud.langfuse.com` (ou URL do seu servidor corporativo).
2. Forneça sua **Public Key** (`pk-lf-...`) gerada em *Settings > API Keys*.
3. Forneça sua **Secret Key** (`sk-lf-...`).

As credenciais são salvas de forma segura no arquivo global do usuário:
- **Linux**: `~/.gemini/antigravity-cli/langfuse.json`
- **Windows**: `%USERPROFILE%\.gemini\antigravity-cli\langfuse.json`

### 2. Configurando para Langfuse Local (Docker)
No assistente, selecione a opção **2 (Langfuse Local)**:
1. Suba os containers na raiz do plugin:
   ```bash
   docker compose up -d
   ```
2. O assistente validará a saúde do serviço em `http://localhost:3000` e configurará as chaves padrão autogeradas:
   - Public Key: `pk-lf-antigravity-cli-public`
   - Secret Key: `sk-lf-antigravity-cli-secret`

---

## 🔧 Configuração Não-Interativa (CI/CD ou Scripts)

Você pode configurar diretamente via flags de linha de comando:

```bash
# Configuração Remota:
node scripts/setup.mjs --remote --host "https://cloud.langfuse.com" --public-key "pk-lf-xxx" --secret-key "sk-lf-xxx"

# Configuração Local:
node scripts/setup.mjs --local

# Verificar status da configuração atual:
node scripts/setup.mjs --status
```

---

## 🎛️ Cascata de Resolução de Configuração

O plugin busca as configurações de conexão na seguinte ordem de prioridade:

1. **Variáveis de Ambiente** (`LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`).
2. **Arquivo do Workspace** (`.langfuse.env` ou `.env` na raiz do projeto ativo).
3. **Arquivo de Configuração Global** (`~/.gemini/antigravity-cli/langfuse.json`).
4. **Fallback Local Padrão** (`http://localhost:3000`).

---

## 🔍 Verificação e Dashboards

Após executar tarefas ou subagentes no Antigravity CLI, você pode verificar o status e integridade da telemetria com:

```bash
python scripts/provision_dashboard.py
```

### Visualização no Painel do Langfuse:
- Acesse `https://cloud.langfuse.com` ou `http://localhost:3000`.
- Vá para a aba **Traces**.
- Filtre por:
  - `tag: feature:*` (Lista todas as features)
  - `tag: feature:adrs-standardization`
  - `tag: stage:tasks`
  - `tag: subagent`
- Abra qualquer trace para ver a árvore completa de execução, gerações do modelo e chamadas de subagentes aninhadas com seus respectivos custos.

---

## 📄 Licença

MIT License. Desenvolvido para o ecossistema Antigravity & StartupOS.
