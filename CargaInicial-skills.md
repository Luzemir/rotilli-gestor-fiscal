# Blueprint de Carga Inicial — Engenharia de Software

Você está atuando como um **Arquiteto de Software Sênior**. O objetivo deste documento é guiar a configuração inicial de um novo projeto do zero, estabelecendo uma estrutura de pastas ideal, segura, testada e pronta para versionamento no GitHub.

Siga rigorosamente o passo a passo abaixo de forma sequencial.

---

## 🔌 Passo 1: Instalação das Skills no Projeto

Abra o terminal integrado do workspace e instale as skills do repositório *Antigravity Awesome Skills* localmente na pasta oculta do agente.

Execute o seguinte comando:

```bash
npx antigravity-awesome-skills --path .agent/skills
```

---

## 🛠️ Passo 2: Engatilhar o Pacote de Produção, Superpowers & Ferramentas

Prepare o ambiente de IA combinando o pacote de skills conceituais com ferramentas operacionais avançadas de terminal. Ative o ecossistema conectando as seguintes camadas:

### 1. Ferramentas Operacionais de Baixo Nível

**agent-skills** (Addy Osmani): Habilite o uso de capacidades operacionais básicas para leitura controlada do ambiente local e manipulação de arquivos.

### 2. Autonomia de Terminal & Resiliência

**superpowers** (obra/superpowers): Forneça ao agente habilidades avançadas de execução em bash, permitindo que ele rode comandos de terminal com capacidade de auto-correção (self-healing), leitura adaptativa de logs de erro e loops de feedback para garantir que as instalações iniciais não falhem.

### 3. Pacote Base de Skills Antigravity

- **Planejamento & Design:** `@brainstorming`, `@senior-architect` (C4 Model)
- **Desenvolvimento & Regras:** `@backend-dev-guidelines`, `@typescript-expert` (ou a linguagem principal), `@react-best-practice` (ou equivalente do front-end)
- **Infraestrutura & Segurança:** `@api-security-best-practices`, `@docker-expert`
- **QA, Documentação & CI/CD:** `@test-driven-development`, `@doc-coauthoring`, `@workflow-automation`
- **Economia de Tokens:** `@ponytail`

### 4. Skills Específicas do Ecossistema gestcon.com.br

> Ative quando o projeto for um app destinado ao ecossistema **gestcon.com.br** (contabilidade, gestão, controle fiscal).

**`gestcon-novo-app`** (`.agent/skills/gestcon-novo-app/SKILL.md`): guia completo de infraestrutura para publicar um novo app Streamlit/Python no ecossistema gestcon.com.br. Cobre:

- Setup único: Railway (conta, plano Hobby, cartão), Vercel (hub), DNS gestcon.com.br
- Estrutura de repositório: pastas, arquivos obrigatórios e templates prontos para copiar  
  (`Procfile`, `railway.toml`, `requirements.txt`, `.streamlit/config.toml`, `secrets.toml`, `.env.example`, `.gitignore`, `pyrightconfig.json`, `app.py`, `_config.py`)
- Deploy Railway: serviço, variáveis de ambiente, volume SQLite, domínio personalizado
- Integração no hub Vercel: card HTML na landing page
- Checklist de verificação pós-deploy (8 pontos)
- Armadilhas conhecidas: SQLite sem volume, cache `__pycache__` stale, `pd.None → NaN`, `st.rerun()`, secrets no git

**Quando acionar:** ao iniciar qualquer app novo do ecossistema gestcon, execute a skill antes da criação dos arquivos de código. Ela define a sequência e os templates corretos.

---

## 🧠 Passo 3: Início do Planejamento (Sessão de Descoberta)

Ative imediatamente a skill `@brainstorming`.

Conduza uma entrevista curta fazendo as perguntas necessárias sobre:

- O que vamos construir (escopo do produto)
- Stack tecnológica detalhada
- Modelo de banco de dados e regras de negócios críticas

> **Para projetos gestcon:** antes de finalizar o planejamento, consulte a skill `gestcon-novo-app` para confirmar que o stack escolhido é compatível com a arquitetura Vercel + Railway definida para o ecossistema. Se o app for Streamlit/Python, a infraestrutura já está resolvida pela skill.

Após coletar as respostas, consolide o planejamento gerando o documento principal `Project.md` (Decision Log) na raiz do projeto.

---

## 📁 Passo 4: Estrutura Automatizada, Validação e Versionamento

Após a aprovação do `Project.md`, utilize as capacidades operacionais combinadas (`agent-skills` + `superpowers`) para automatizar e validar o ambiente de desenvolvimento local:

### 1. Árvore de Diretórios

**Para projetos genéricos** — estrutura padrão da indústria:

```
├── src/
├── tests/
├── docs/
├── config/
```

**Para projetos gestcon (Streamlit/Python)** — use a estrutura definida na skill `gestcon-novo-app`:

```
gestcon-<slug>/
├── app.py
├── _config.py
├── pages/
├── src/
│   ├── core/
│   └── db/
├── .streamlit/
├── assets/
├── scripts/
├── tests/
├── Procfile
├── railway.toml
├── requirements.txt
├── packages.txt          ← somente se usar lxml ou libs de sistema
├── .env.example
├── pyrightconfig.json
└── .gitignore
```

### 2. Execução Resiliente de Setup

Utilize as ferramentas do `superpowers` para rodar comandos de inicialização do projeto (ex: `npm init`, `pnpm init` ou setup da linguagem escolhida). Se o terminal retornar algum erro de ambiente, use o loop de auto-correção para resolver antes de prosseguir.

### 3. Proteção do Repositório (`.gitignore`)

Crie um arquivo `.gitignore` robusto na raiz que bloqueie rigorosamente:

- Dependências de pacotes (ex: `node_modules/`)
- Arquivos de ambiente e chaves locais (ex: `.env`, `.env.local`)
- A pasta local de agentes (`.agent/`), impedindo a subida de logs, chaves ou arquivos temporários das skills para o repositório remoto
- **Para projetos gestcon:** adicione também `*.db`, `src/db/`, `.streamlit/secrets.toml`, `Documentos/`, `logs/`

### 4. Inicialização do Git

Execute os comandos de terminal necessários para:

1. Iniciar o repositório: `git init`
2. Adicionar a estrutura com o `.gitignore`
3. Criar o primeiro commit seguindo o padrão de Conventional Commits:

```bash
git commit -m "chore: initial project structure, baseline configuration and decision log"
```

---

## 🚀 Passo 5: Deploy no Ecossistema gestcon.com.br

> **Aplica-se apenas a projetos gestcon.** Para outros projetos, ignore este passo.

Com o repositório criado e commitado, execute as Fases 2, 3 e 4 da skill `gestcon-novo-app`:

1. **Fase 2** — Criar serviço no Railway: conectar repo, configurar env vars (`DB_PATH`, `AUTH_USER_*`), adicionar volume `/data` para SQLite, apontar domínio `<slug>.gestcon.com.br`
2. **Fase 3** — Registrar no hub Vercel: adicionar card do app em `gestcon-hub/index.html`
3. **Fase 4** — Executar checklist de verificação pós-deploy (build, login, HTTPS, persistência do banco, aparição no hub)

> Referências rápidas de deploy:
> - Dashboard Railway: https://railway.app/dashboard  
> - Dashboard Vercel: https://vercel.com/luzemir-contilicoms-projects  
> - App modelo: `c:\APP\Rotilli_GestorFIscal\src\streamlit\`

---

## ⚠️ Nota de Execução

Não pule etapas. Garanta que o **Passo 3** (aprovação do `Project.md`) seja concluído antes de iniciar as escritas físicas de código e execução de comandos do **Passo 4**. Para projetos gestcon, a skill `gestcon-novo-app` deve ser lida **antes** de criar qualquer arquivo — ela define os templates canônicos e evita retrabalho.
