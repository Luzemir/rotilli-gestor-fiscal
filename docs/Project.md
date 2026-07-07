# Project.md (Decision Log) — Rotilli Gestor Fiscal

## Objetivo e Escopo

Automatizar o cálculo do ICMS Substituição Tributária com base no Crédito Outorgado
(Termo de Acordo Rotilli × Sefaz/MS). O sistema substitui as macros de Excel (.xlsm)
por um app web que importa NF-e (XML), consulta a tabela CMED da Anvisa, aplica as
regras de classificação (MOD BC 0–5) e gera a planilha de apuração mensal.

> Detalhes operacionais, schema do banco, regras de negócio e armadilhas conhecidas:
> ver `AGENTS.md` na raiz (mantido como fonte de verdade para continuidade).

---

## Decisões de Arquitetura

### D1 — Stack (revisada 2026-06, registrada 2026-07-07)
**Decisão original (2026-06 início):** Next.js + Node + PostgreSQL/Supabase + Vercel.
**Decisão vigente:** **Python + Streamlit + SQLite + Railway.**
**Motivo da mudança:** todo o pipeline (parser XML, ETL CMED, geração de .xlsm com
openpyxl) já estava em Python; Streamlit eliminou a necessidade de API separada e
frontend próprio. SQLite é suficiente para o volume (1 empresa, ~milhares de
registros/mês) e viaja como arquivo único entre ambientes (página Admin faz
upload/download do banco).

### D2 — Competência da importação (2026-06-16, revisada 2026-07-06)
A competência dos XMLs é definida **pelo operador** (seletor Ano/Mês na importação),
não pela data de emissão de cada nota. NF-e emitida no fim do mês anterior mas
recebida no lote atual entra na apuração do mês atual. (Antes era pelo nome da pasta
`AAAA-MM`; o seletor substituiu isso quando a importação virou upload web.)

### D3 — Snapshot de apuração (2026-06-16)
Cada item importado é congelado em `nfe_item_apuracao` (PMC/MVA/MOD do momento da
importação). A planilha é sempre regenerada do banco (acumulado da competência),
clonando o template — reimportar o mesmo XML sobrescreve a mesma linha (idempotente).

### D4 — PMC histórico vs CMED (2026-06-16)
A coluna Y (PMC) da planilha é SEMPRE o PMC histórico do produto. O valor pesquisado
na CMED vai em coluna própria (AN) com a diferença em AO — a CMED nunca sobrescreve
o histórico automaticamente.

### D5 — Fórmulas vivas na planilha (2026-06-16)
As 8+ fórmulas de cálculo (AD–AK, AO, AP) são escritas como fórmula Excel literal
(replicadas da planilha histórica), não como valores calculados em Python — o
operador confere e o Excel recalcula.

### D6 — Autenticação própria + sessão por token (2026-07-02)
Login por tabela `usuarios` no SQLite (gestão via página Admin) com fallback em env
vars. Sessão persistida em tabela `sessoes` + token na URL (`?s=`) para sobreviver a
F5 — Streamlit não tem sessão nativa entre reloads.

### D7 — Reset do histórico Git (2026-07-06)
O repositório esteve público com documentos fiscais e contratuais reais commitados.
Histórico integralmente reescrito (commit único), `Documentos/` adicionada ao
`.gitignore`, tag antiga removida do remoto. Backup do histórico antigo preservado
fora do repositório.

### D8 — Colunas Seguro/IPI e Alíquota (2026-07-06)
- Coluna T = "SEGURO/DESP. ACESS." (vSeg + vOutro, rateio proporcional quando o valor
  só existe no total da nota)
- Coluna U = "IPI" (vIPI real do item; antes recebia vOutro por engano histórico)
- Coluna AP = "ALÍQUOTA DO PRODUTO" (X/W, conferência manual)
- Dados de competências importadas antes desta data mantêm o formato antigo até
  reimportação dos XMLs.

---

## Fluxo Mensal (vigente)

1. Operador acessa o app (Railway), página **Importar NF-e**
2. Seleciona Ano/Mês e arrasta a pasta de XMLs do mês
3. Sistema classifica cada item pelo cadastro; produtos novos viram **Alertas**
4. Operador classifica os alertas (com sugestão automática do motor de pré-classificação)
5. Reimporta/regera a planilha da competência e baixa o .xlsm (trilha Original)
6. Trilha Ajustada e envio por e-mail: pendentes (ver AGENTS.md → Pendências)
