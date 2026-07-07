# AGENTS.md — Contexto de Continuidade para IAs
# Rotilli Gestor Fiscal — Automação de ICMS Substituição Tributária (Crédito Outorgado)

> Última revisão geral: 2026-07-07. Este documento descreve o estado REAL do
> projeto. Se algo aqui divergir do código, o código vence — atualize este arquivo.

## 🎯 OBJETIVO

Substituir o processo manual em planilhas Excel (.xlsm com macros) por um app web que:
1. Importa XMLs de NF-e do mês (upload drag-and-drop da pasta inteira)
2. Classifica os itens por tipo de tributação (MOD BC 0–5) usando o cadastro histórico
3. Consulta a tabela CMED da Anvisa (PMC 17% — alíquota MS) por competência
4. Gera a planilha de apuração ICMS-ST por Crédito Outorgado (Termo de Acordo Rotilli × Sefaz/MS), trilha Original
5. Alerta produtos novos para classificação manual antes do fechamento

---

## 🏗️ STACK REAL (não confundir com planos antigos)

- **Python 3.12 + Streamlit 1.58** — frontend e backend num só processo
- **SQLite** — arquivo único; local em `src/db/gestor_fiscal.db`, produção no volume Railway via env `DB_PATH`
- **openpyxl** (keep_vba=True) — geração da planilha .xlsm a partir de template
- **Deploy: Railway** — auto-deploy a cada push no `master` (GitHub `Luzemir/rotilli-gestor-fiscal`)
  - `Procfile`: `web: streamlit run src/streamlit/app.py ...`
  - Env vars: `DB_PATH=/data/gestor_fiscal.db` (volume), `AUTH_USER_*`/`AUTH_NAME_*`/`AUTH_PERFIL_*`
  - Acesso: `https://bit.ly/ctlplancrout` → `web-production-8c3583.up.railway.app`
- **Autenticação**: tabela `usuarios` (SHA-256) gerida pela página Admin + fallback env vars.
  Sessão persistente via token na URL (`?s=`) validado na tabela `sessoes` (expira em 30 dias) — sobrevive a F5.

> ⚠️ O plano original (Next.js + Node + Supabase/PostgreSQL + Vercel) foi ABANDONADO.
> Não existe API separada — o antigo `src/api/` (FastAPI) foi removido em 2026-07-07 por
> estar morto e divergente.

---

## 📂 ESTRUTURA REAL

```
c:\APP\Rotilli_GestorFIscal\
├── .agent/              # ⛔ git-ignored — skills de IA locais
├── data/                # ⛔ git-ignored — XMLs (data/nfe/AAAA-MM/), CMED, xlsx de apoio
├── Documentos/          # ⛔ git-ignored — contratos, planilhas fiscais reais, specs (NUNCA COMMITAR)
├── docs/Project.md      # Decision log
├── scripts/             # ETL e utilitários (rodar da raiz)
├── src/
│   ├── core/            # Lógica de negócio (ver seção módulos)
│   ├── db/              # gestor_fiscal.db + backups/ (git-ignored)
│   └── streamlit/       # App: _config.py, app.py, pages/
├── static/logo_contili.png
├── templates/RegimeEspecialMS_template.xlsm  # clonado a cada geração de planilha
└── tests/               # pytest
```

---

## 🖥️ PÁGINAS DO APP (src/streamlit/pages/)

| Página | Função |
|---|---|
| `app.py` (Painel Geral) | KPIs, últimas NF-e, alertas pendentes, navegação |
| `0_Admin.py` | Somente perfil Administrador: gestão de usuários, upload/download do banco entre ambientes, info do ambiente |
| `1_Importar_NF_e.py` | Seletor Ano/Mês + upload múltiplo de XMLs (arrastar a pasta inteira funciona — react-dropzone coleta recursivo). Salva em `data/nfe/{AAAA-MM}/`, parseia, classifica, persiste em `nfe_item_apuracao`, gera planilha da competência com botão de download |
| `2_Alertas.py` | Classificação manual de produtos novos (MOD/PMC/MVA), sugestão automática, classificação em lote, botão "usar similar" |
| `3_Produtos.py` | Busca, histórico por competência (clicável), edição de classificação histórica, upload mensal validado das planilhas Original/Ajustada (popup de rejeição via `st.dialog`), importação em lote |
| `4_CMED.py` | Status por competência, importação de arquivos CMED, consulta por EAN (todas as competências) |
| `5_NCM_ST.py` | Pesquisa NCM/CEST (raiz e abrangência), CRUD individual via dialogs (➕ Novo / ✏️ Editar / 🗑️ Excluir), atualização em lote via CSV-patch, export CSV. Raspagem Econet: em desenvolvimento |
| `6_Comparar_Planilhas.py` | Divergências entre planilha do App e a Ajustada do operador |

`_config.py` centraliza: tema CSS Contili, `st.logo`, autenticação/sessões, `get_conn()`,
`init_*_table()` (todas chamadas em `init_todas_tabelas()` no startup do app.py — mas
`init_sessoes_table()` também roda dentro de `autenticar()` porque as outras páginas não
passam pelo app.py), JS que esconde Admin para não-admins e renomeia 'app'→'Painel Geral'.

---

## 🗄️ BANCO (tabelas principais)

| Tabela | Conteúdo | Chave |
|---|---|---|
| `produtos` | Parte fixa do cadastro (~2.3k) | cnpj_remetente + cod_produto_origem |
| `produto_competencia` | Classificação por mês (MOD/PMC/MVA), só grava quando muda (dedup) | + mes_ano + tipo_planilha |
| `cmed_historico` | Tabela Anvisa por competência (~128k, 2026-01→05) | ean + mes_ano |
| `produto_alerta` | Produtos novos pendentes, com pré-classificação (pre_mod_bc/pre_pmc/pre_mva/pre_nota) | id; UNIQUE(cnpj_emitente, cod_produto) |
| `nfe_item_apuracao` | Snapshot de cada item de NF-e importado (fonte da planilha) | chave_acesso + num_item + tipo_planilha |
| `ncm_st` | Subanexo ICMS-ST MS: NCM/CEST/seguimento/MVAs por alíquota | id |
| `usuarios` / `sessoes` | Login e sessões persistentes | — |

---

## 📐 REGRAS DE NEGÓCIO ESSENCIAIS

### MOD BC ICMS ST (0–5)
| Código | Nome | Critério |
|---|---|---|
| 0 | PMC | NCM/CEST no Subanexo ST + EAN na CMED com PMC 17% > 0 |
| 1/2/3 | Lista Positiva/Negativa/Neutra | No Subanexo + EAN na CMED, PMC=0 → roteia pela lista |
| 4 | MVA | No Subanexo ST, EAN fora da CMED. MVA escolhido pela alíquota efetiva de origem (interna ≥15% / 12 / 7 / 4) |
| 5 | Normal | Fora do Subanexo ST |

- **MVA é sempre fração decimal** (0,3824 = 38,24%). A fórmula da coluna AD exige `Z<=5`;
  `_normalizar_mva()` divide por 100 qualquer valor >5 (erro de digitação como percentual cheio).
- **Competência**: definida pelo seletor Ano/Mês na importação (não mais pelo nome da pasta,
  nem pela data de emissão). Todos os XMLs do lote entram na competência selecionada.
- **PMC coluna Y** = histórico do produto, NUNCA sobrescrito pela CMED; o valor CMED vai na AN,
  a diferença na AO.

### Planilha gerada (aba RegimeEspecial, tabela `tabRegEsp`, A4:AP)
- Colunas literais A–AC + AN; fórmulas vivas AD–AK, AO, AP (replicadas do Excel histórico)
- `T` = "SEGURO/DESP. ACESS." (vSeg + vOutro somados, com rateio proporcional se só no total da nota)
- `U` = "IPI" (vIPI real do item — corrigido 2026-07-06; antes era só vOutro)
- `AP` = "ALÍQUOTA DO PRODUTO" (`=X/W`, percentual) — última coluna, para conferência manual
- ⚠️ **Ao editar o template**: nomes de coluna da Excel Table ficam em DOIS lugares —
  a célula do cabeçalho (linha 4) E `ws.tables['tabRegEsp'].tableColumns[i].name`.
  Atualizar os dois, senão o Excel acusa "conteúdo ilegível".

### Pré-classificação — 3 CÓPIAS DELIBERADAS
A mesma árvore de decisão existe em `nfe_parser._pre_classificar`,
`1_Importar_NF_e._aplicar_pre_classificacao` e `2_Alertas._reclassificar_alerta`.
Motivo: cache `__pycache__` stale no Streamlit já serviu versão antiga de `src/core`
(sintoma: .py correto, comportamento antigo). Ao alterar a regra, **alterar as três**
— há teste de consistência em `tests/` que compara as cópias.

---

## ⚙️ SCRIPTS (rodar da raiz)

| Script | Uso |
|---|---|
| `build_database.py` | Recarga histórica completa (`--confirmar` faz backup + wipe + reimporta de Documentos/AAAA-MM/) |
| `backup_and_reset_competencias.py` | Backup do BD em `src/db/backups/` + limpeza |
| `cmed_downloader.py` | Import de arquivos CMED (download automático não funciona — site da Anvisa é JS; baixar manualmente) |
| `scraper_econet_ncm_st.py` + `check_econet_state.py` + `launch_chrome_debug.bat` | Raspagem Econet via Chrome CDP porta 9222 (uso local, em desenvolvimento) |
| `preparar_template_regime_especial.py` | Pontual — gerou o template a partir do histórico 2026-04 |
| `comparar_planilhas.py` | Versão CLI da página 6 |

---

## 🔒 SEGURANÇA E GIT

- Histórico do repositório foi **ZERADO em 2026-07-06** (dados fiscais reais estavam expostos
  em repo público). `Documentos/` inteira está no `.gitignore` — **nunca commitar**.
- `secrets.toml` git-ignored (só o `.example` vai pro repo). Senhas de app: tabela `usuarios`
  (hash SHA-256 sem salt — aceitável para app interno; migrar p/ bcrypt se expor mais).
- Commits: conventional commits em português (`feat:`, `fix:`, `chore:`).

## ⚠️ ARMADILHAS CONHECIDAS

1. **`__pycache__` stale** no Streamlit Cloud/local — lógica crítica duplicada nas páginas (ver acima).
2. **pandas NaN vs None** — `pd.DataFrame(lista_de_dicts)` converte None→NaN; usar `_safe_num`/`_safe_int`/`pd.isna` antes de comparar ou gravar.
3. **`st.session_state` + widgets** — mudança de estado que afeta widget acima exige `st.rerun()` explícito.
4. **Excel Table metadata** — ver seção Planilha.
5. **Ambiente Railway é headless** — nada de tkinter/seletor de arquivos do SO; só `st.file_uploader`.

## 🏁 PENDÊNCIAS REAIS

1. **Trilha Ajustada** da planilha (replicar a geração da Original)
2. **Reimportar XMLs de 2026-05** — registros antigos têm seguro/IPI no formato pré-correção de 2026-07-06 e `bc_icms_st_nfe`/`vlr_icms_st_nfe` NULL
3. **Envio por e-mail ao fiscal** (formato: mesmo Excel `Rotili - EnvioFiscal-...`? — em aberto)
4. **Raspagem Econet** (página NCM ST, seção 3 — "em desenvolvimento")
5. Limitação conhecida: competência cross-month por data de emissão na trilha automática antiga — resolvida pelo seletor Ano/Mês

## ✅ CONVENÇÕES

- Idioma: português do Brasil em tudo (código, comentários, UI, commits)
- Nada solto na raiz: docs em `docs/`, scripts em `scripts/`, código em `src/`
- Não altere o que não foi pedido; preserve lógica existente
