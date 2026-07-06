# AGENTS.md — Contexto de Continuidade para IAs
# Rotilli Gestor Fiscal — Automação de ICMS Substituição Tributária

## 🎯 OBJETIVO DO PROJETO
Substituir o processo manual feito em planilhas Excel (.xlsm com macros) por uma aplicação automatizada que:
1. Importa XMLs de Notas Fiscais Eletrônicas (NF-e)
2. Classifica os itens de cada nota por tipo de tributação (PMC, MVA, Positivo, Negativo, Neutro, Normal)
3. Consulta a tabela CEMED da Anvisa para buscar o PMC atualizado mensalmente
4. Gera a apuração do ICMS-ST baseado no Crédito Outorgado, conforme Termo de Acordo Rotilli x Sefaz/MS
5. Gera relatórios no padrão das planilhas históricas (Original e Ajustada)

---

## 📂 ESTRUTURA DE PASTAS DO PROJETO
```
c:\APP\Rotilli_GestorFIscal\
│
├── .agent/              # ⛔ IGNORADO NO GIT — Skills de IA instaladas (npx antigravity-awesome-skills)
├── .github/             # CI/CD (vazio por enquanto)
├── .gitignore           # Bloqueia: .agent/, data/, node_modules, .env, build/
│
├── docs/
│   └── Project.md       # Decision Log principal do projeto
│
├── scripts/             # Scripts Python de ETL e automação (rode sempre da raiz do projeto)
│   ├── build_database.py    # CONCLUÍDO — Carga inicial do BD a partir das planilhas históricas
│   ├── cmed_downloader.py   # EM ANDAMENTO — Download e import da tabela CMED da Anvisa
│   └── _check_db.py         # Utilitário para checar estado do BD (pode apagar quando quiser)
│
├── src/
│   ├── app/             # 🔲 VAZIO — Futuro frontend (Next.js ou app Python)
│   ├── components/      # 🔲 VAZIO — Componentes de UI
│   ├── core/            # 🔲 VAZIO — Lógica de negócio e parser de XML NF-e
│   ├── db/
│   │   └── gestor_fiscal.db # ✅ BANCO DE DADOS SQLite criado e populado
│   └── tests/           # 🔲 VAZIO — Testes unitários
│
├── assets/              # 🔲 VAZIO — Imagens e ícones
├── data/                # ⛔ IGNORADO NO GIT — Pasta para XMLs e CMED temporários
│   └── cmed/            # Coloque aqui o arquivo .xls baixado manualmente da Anvisa
│
└── Documentos/          # Arquivos de referência do negócio (NÃO ALTERAR)
    ├── MapaInicial.docx         # Escopo e módulos do projeto
    ├── Processo.docx            # Descrição detalhada do fluxo manual atual
    ├── Tabela de Produtos.docx  # Especificação do schema da tabela de produtos
    ├── Decreto 12415-2007.pdf   # Legislação base do ICMS-ST no MS
    ├── Resolução 2566-2014.pdf  # Legislação base do Crédito Outorgado
    ├── TA_ROTILLI_ASSINADO...   # Termos de acordo com a Sefaz (dois arquivos)
    └── 2025-06/ a 2026-04/      # Planilhas mensais históricas (Originais e Ajustadas)
```

---

## 🗄️ BANCO DE DADOS (src/db/gestor_fiscal.db)
**Motor:** SQLite (arquivo único, sem servidor)
**Localização:** `src/db/gestor_fiscal.db`

### Tabela: `produtos` (Parte Fixa)
| Coluna              | Tipo | Descrição                             |
|---------------------|------|---------------------------------------|
| cnpj_remetente      | TEXT | CNPJ do fornecedor (chave composta)   |
| cod_produto_origem  | TEXT | Código do produto na NF (chave composta) |
| descricao_produto   | TEXT | Nome do produto                       |
| unidade             | TEXT | Unidade de medida                     |

**Status:** ✅ Populada com **2.335 produtos únicos** extraídos do histórico 06/2025–04/2026

---

### Tabela: `produto_competencia` (Parte Incremental)
| Coluna              | Tipo | Descrição                                          |
|---------------------|------|----------------------------------------------------|
| cnpj_remetente      | TEXT | FK para `produtos`                                 |
| cod_produto_origem  | TEXT | FK para `produtos`                                 |
| mes_ano             | TEXT | Competência no formato `YYYY-MM`                   |
| mod_bc_icms_st      | TEXT | 0=PMC, 1=Negativo, 2=Positivo, 3=Neutro, 4=MVA, 5=Normal |
| pmc                 | REAL | Valor do PMC utilizado naquele mês                 |
| mva                 | REAL | Percentual MVA utilizado naquele mês               |
| tipo_planilha       | TEXT | "Original" ou "Ajustada"                           |

**Status:** ✅ Populada com **4.274 registros** (reimportação 2026-06-16 com deduplicação — ver nota abaixo)
**Distribuição atual de mod_bc_icms_st:**
- `0` (PMC): 933 registros
- `1` (Negativo): 122 registros
- `2` (Positivo): 22 registros
- `3` (Neutro): 182 registros
- `4` (MVA): 1.313 registros
- `5` (Normal/Consumo): 1.702 registros

> **Nota sobre deduplicação (2026-06-16):** o import histórico antigo gravava uma linha por
> competência para TODO produto, mesmo sem mudança de classificação (chegou a 7.961 registros).
> Além disso, o arquivo `Rotili - EnvioFiscal-RegimeEspecialMS_YYYY_MM.xlsx` de cada mês também
> tem uma aba `RegimeEspecial` e estava sendo varrido junto, podendo sobrescrever a planilha
> Original legítima. O banco foi reconstruído do zero (backup automático em
> `src/db/backups/`) usando `scripts/build_database.py --confirmar`, que agora:
> - Ignora explicitamente os arquivos `Rotili - EnvioFiscal-...`
> - Grava uma nova linha em `produto_competencia` **somente** quando `mod_bc_icms_st` ou `mva`
>   mudam em relação à última competência conhecida daquele produto+trilha (`pmc` não entra
>   nessa comparação — vem da CMED)
> - Processa todas as planilhas **Original** em ordem cronológica, depois todas as **Ajustada**
> - Lógica centralizada em `src/core/competencia_importer.py`, reusada pela tela de upload
>   mensal em **Produtos** (ver seção 4 do backlog)

---

### Tabela: `cmed_historico` (Tabela da Anvisa)
| Coluna       | Tipo | Descrição                              |
|--------------|------|----------------------------------------|
| ean          | TEXT | Código de barras EAN do medicamento    |
| produto      | TEXT | Nome do medicamento                    |
| apresentacao | TEXT | Apresentação/dosagem                   |
| pmc_17       | REAL | PMC para alíquota 17% (Mato Grosso do Sul) |
| tipo_lista   | TEXT | Positiva / Negativa / Neutra           |
| mes_ano      | TEXT | Competência no formato `YYYY-MM`       |

**Status:** ✅ **Populada com 128.320 registros** — 5 competências (2026-01 a 2026-05) carregadas de `Documentos/CEMED/`

| Competência | Registros |
|-------------|-----------|
| 2026-01     | 26.740    |
| 2026-02     | 26.954    |
| 2026-03     | 24.502    |
| 2026-04     | 25.021    |
| 2026-05     | 25.103    |

> Arquivos baixados manualmente de https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos
> Vigência identificada pelo padrão `xls_conformidade_site_YYYYMMDD_*.xlsx` no nome do arquivo.

---

## ⚙️ SCRIPTS DISPONÍVEIS
> Todos os scripts devem ser executados a partir da **raiz** do projeto:
> `c:\APP\Rotilli_GestorFIscal\`

### 1. `scripts/build_database.py` ✅ CONCLUÍDO (reescrito 2026-06-16)
- Uso: `python scripts/build_database.py` (dry-run, só mostra o que faria) ou
  `python scripts/build_database.py --confirmar` (faz backup, limpa e reimporta de fato)
- Varre `Documentos/YYYY-MM/*.xls*`, reconhece nomes históricos tolerantes (sem sufixo,
  hífen/underscore, "Ajustado"/"Ajustada") via `classificar_arquivo_historico` em
  `src/core/competencia_importer.py`, e **ignora explicitamente** qualquer arquivo
  `Rotili - EnvioFiscal-...` (tinha aba `RegimeEspecial` igual e contaminava os dados)
- Processa todas as planilhas **Original** em ordem cronológica, depois todas as **Ajustada**
- Backup automático em `src/db/backups/gestor_fiscal_YYYYMMDD_HHMMSS.db` antes de qualquer wipe
  (via `scripts/backup_and_reset_competencias.py`)
- Extrai colunas G, M, O, P (parte fixa) e Y, Z, AA (PMC/MVA/mod_bc, parte incremental)
- Usa a aba "RegimeEspecial" (fallback para a primeira aba), pula as 2 primeiras linhas

### 2. `src/core/competencia_importer.py` ✅ NOVO (2026-06-16)
- Módulo central de import, reusado pelo script acima E pela tela de upload mensal em **Produtos**
- `importar_competencia(conn, fonte, mes_ano, tipo_planilha)` — grava uma linha em
  `produto_competencia` **somente** se `mod_bc_icms_st` ou `mva` mudaram em relação à última
  competência conhecida daquele produto+trilha (idempotente: reimportar a mesma competência
  duas vezes dá o mesmo resultado)
- `validar_nome_upload(nome, ano, mes, tipo)` — valida uploads novos contra o padrão estrito
  `RegimeEspecialMS_AAAA_MM_Original.xlsx` / `..._Ajustada.xlsx` (`.xlsm` também aceito)

### 2. `scripts/cmed_downloader.py` ⚠️ EM ANDAMENTO
- Tenta fazer download automático via web scraping do site `gov.br/anvisa`
- **PROBLEMA ATUAL:** O site usa JavaScript dinâmico, então o link `.xls` não aparece no HTML estático. O script já tem fallback: se existir um arquivo em `data/cmed/*.xls*`, ele usa esse arquivo.
- **PRÓXIMO PASSO:** O usuário precisa baixar manualmente o arquivo CMED do site da Anvisa e salvar em `data/cmed/`. O script então processa automaticamente.
- A URL de onde baixar é: `https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos`
- A coluna de interesse é: **"PMC 17%"** (alíquota do MS)

---

## 🔄 FLUXO DO PROCESSO MENSAL (O QUE O APP DEVE FAZER)
```
1. Usuário coloca os XMLs das NF-es do mês em data/nfe/YYYY-MM/
2. Sistema lê cada XML e extrai os itens (EAN, código, descrição, CNPJ, valores)
3. Para cada item, busca no BD de Produtos (por cod_produto_origem ou cnpj+cod):
   a. ✅ ENCONTRADO → usa a classificação histórica (mod_bc_icms_st)
      - Se mod_bc = 0 (PMC): compara o PMC do BD com o PMC do CMED atual
        - Se diferente: atualiza o PMC e re-calcula
        - Se igual: usa o valor do BD
   b. ⚠️ NÃO ENCONTRADO → ALERTA VISUAL para o operador classificar manualmente
4. Sistema aplica as fórmulas de cálculo ICMS-ST conforme cada mod_bc
5. Gera planilha "Original" e planilha "Ajustada"
6. Gera arquivo de envio ao fiscal por e-mail
```

---

## 📐 REGRAS DE NEGÓCIO (mod_bc_icms_st)
| Código | Nome       | Critério                                               | Base de Cálculo |
|--------|------------|--------------------------------------------------------|-----------------|
| 0      | PMC        | Produto consta na tabela CMED com PMC                  | Valor do PMC 17% da CMED |
| 1      | Negativo   | Produto na Lista Negativa CMED                         | PMC com redução |
| 2      | Positivo   | Produto na Lista Positiva CMED                         | PMC com acréscimo |
| 3      | Neutro     | Produto na Lista Neutra CMED                           | PMC sem variação |
| 4      | MVA        | Produto tem ST mas NÃO está na CMED (sem PMC)          | Margem de Valor Agregado (%) |
| 5      | Normal     | Produto sem ST (consumo interno) ou não sujeito ao ST  | Sem ICMS-ST     |

**Classificações são separadas em Original (conforme legislação) e Ajustada (decisão do operador).**

---

## 🏗️ O QUE FALTA CONSTRUIR (Backlog Priorizado)

### 🔴 URGENTE (Próximo Sprint — CONCLUÍDO)
1. ~~**Limpar registros inválidos no BD**~~ ✅ **CONCLUÍDO** — 19 registros com `mod_bc_icms_st = 'MOD BC ICMS ST'` foram removidos. BD está limpo.

2. ~~**Módulo de Import CMED**~~ ✅ **CONCLUÍDO** — 128.320 registros carregados de `Documentos/CEMED/` (jan–mai 2026). Script aceita `--pasta` e `--todos`. Arquivos devem ser baixados manualmente de `https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos` e salvos em `Documentos/CEMED/`.

3. ~~**Módulo de Parsing de XML (NF-e)**~~ ✅ **CONCLUÍDO** — `src/core/nfe_parser.py` criado.
   - Roda com: `python src/core/nfe_parser.py --pasta data/nfe/2026-05`
   - Parseia namespace `nfe` completo, extrai EAN/cProd/xProd/NCM/valores
   - Cruza com BD de produtos, retorna classificados e lista de novos
   - Exibe relatório no terminal com alerta de produtos novos
   - Revisão 2026-06-16: estendido para capturar também chave de acesso (via
     `infNFe/@Id` ou `protNFe/infProt/chNFe`), UF/razão remetente, CEST, CFOP,
     nº item, frete/seguro/desconto/outras despesas, e BC/VLR ICMS de origem
     (extração genérica do filho de `imposto/ICMS`, funciona para qualquer
     CST/CSOSN incluindo Simples Nacional)

### 🟡 PRÓXIMO
4. ~~**Lógica de Comparação CMED**~~ ✅ **CONCLUÍDO** — `src/core/cmed_comparador.py` criado.
   - `consultar_pmc_cmed(ean, mes_ano, conn)` busca na CMED com fallback ao mês anterior
   - `comparar_pmc(item, mes_ano, conn)` atualiza o item com status: `PMC_OK | PMC_DIVERGENTE | PMC_SEM_CMED | PMC_SEM_EAN`
   - Integrado ao `nfe_parser.py`: produtos com `mod_bc=0` têm o PMC verificado automaticamente ao processar NF-es
   - Relatório final exibe tabela com divergências (PMC BD vs CMED)

5. ~~**API / Backend**~~ ✅ **CONCLUÍDO** — `src/api/app.py` (FastAPI + uvicorn)
   - `GET  /api/status`          — estatísticas do banco (produtos, CMED, alertas)
   - `POST /api/import/nfe`      — processa XMLs de uma pasta, retorna classificados + PMC divergentes + novos
   - `POST /api/import/cmed`     — carrega arquivo(s) CMED de uma pasta
   - `GET  /api/produtos`        — lista paginada com busca por nome/código
   - `GET  /api/alertas`         — produtos novos detectados em NF-es (filtro por status)
   - `PATCH /api/alertas/{id}`   — atualiza status do alerta (PENDENTE/CLASSIFICADO/IGNORADO)
   - Swagger UI automático em: http://localhost:8000/docs
   - Iniciar: `python src/api/app.py` (ou `uvicorn src.api.app:app --reload`)
   - Tabela `produto_alerta` criada no BD ao subir o servidor

6. ~~**Interface (Frontend)**~~ ✅ **CONCLUÍDO** — Streamlit (`src/streamlit/`)
   - `app.py` — Dashboard: métricas (produtos, CMED, alertas pendentes)
   - `pages/1_Importar_NF_e.py` — processa XMLs, exibe PMC divergentes e novos produtos
   - `pages/2_Alertas.py` — classificação manual (mod_bc, PMC, MVA) + gravação no BD
   - `pages/3_Produtos.py` — busca por nome/código/CNPJ; tabela clicável (`on_select`) exibe histórico de competências do produto selecionado
   - `pages/4_CMED.py` — status por competência, importação e consulta por EAN (mostra TODAS as competências carregadas, não só a mais recente)
   - `.streamlit/config.toml` (raiz do projeto) — `baseFontSize = 18` para melhorar legibilidade das tabelas/métricas
   - Iniciar: `streamlit run src/streamlit/app.py` (rodar a partir da raiz do projeto para o config.toml ser detectado)
   - Revisão 2026-06-16: corrigida busca de produtos (faltava CNPJ), histórico não reagia a clique (agora usa seleção de linha do `st.dataframe`), busca CMED por EAN só trazia a competência mais recente (agora traz o histórico completo)
   - Revisão 2026-06-16 (2): corrigido erro `NotFoundError: insertBefore` causado pelo Google Tradutor automático do Chrome reescrevendo o DOM por fora do React. `_config.py` agora expõe `bloquear_traducao_automatica()` (injeta `translate="no"` + `<meta name="google" content="notranslate">`), chamada no topo de toda página

7. ~~**Importação Mensal Validada de RegimeEspecial**~~ ✅ **CONCLUÍDO** (2026-06-16) — expander
   "📤 Importar nova competência" no topo de `pages/3_Produtos.py`
   - Upload via `st.file_uploader` (Original + Ajustada), nome exigido **exato**:
     `RegimeEspecialMS_AAAA_MM_Original.xlsx` e `RegimeEspecialMS_AAAA_MM_Ajustada.xlsx`
     (`.xlsm` também aceito)
   - Valida: os dois arquivos foram enviados; nome de cada um bate com o padrão; competência
     embutida no nome bate com a caixa Ano/Mês informada; tipo do arquivo bate com o campo
     (detecta arquivos trocados de campo). Qualquer falha rejeita com mensagem específica
     (não genérica) explicando exatamente o que corrigir
   - Botões sequenciais: "1️⃣ Importar Original" habilita após validação; "2️⃣ Importar Ajustada"
     só habilita depois que o Original for importado com sucesso nesta sessão
     (`st.session_state` + `st.rerun()` — sem o rerun explícito o botão não atualiza seu estado
     `disabled` na mesma execução em que o flag é setado)
   - Usa a mesma `importar_competencia()` do script de carga histórica — dedup idêntico

8. ~~**Geração da Planilha de Crédito Outorgado (trilha Original)**~~ ✅ **CONCLUÍDO** (2026-06-16)
   - `src/core/nfe_repository.py` — `persistir_itens()` grava cada item de NF-e importado em
     `nfe_item_apuracao` (idempotente, PK `chave_acesso+num_item+tipo_planilha`; PMC/MVA/mod_bc
     ficam congelados no momento da importação, snapshot)
   - `templates/RegimeEspecialMS_template.xlsm` — template fixo (7 abas), clonado a cada geração;
     gerado por `scripts/preparar_template_regime_especial.py` a partir do arquivo histórico de
     2026-04. Cabeçalho na linha 4, dados a partir da linha 5 (Excel Table `tabRegEsp`)
   - `src/core/planilha_credito_outorgado.py` — `gerar_planilha(conn, mes_ano, tipo_planilha)`:
     lê TODOS os itens já persistidos daquela competência (acumulado de múltiplas sessões de
     importação), escreve dados literais + as 8 fórmulas de cálculo (BC ICMS ST APURADO →
     Aliquota Interna → VLR ICMS ST APURADO → Crédito Outorgado devido → CALC.1/CALC.2 →
     CRÉD.OUTORG. → Valor ICMS a Pagar) **replicadas literalmente** do Excel histórico, como
     fórmula viva (não valor estático). Salva em
     `Documentos/{mes_ano}/RegimeEspecialMS_{ano}_{mes}_{tipo}.xlsm`
   - Fórmulas validadas com a lib `formulas` (motor de cálculo Excel em Python) contra os 3
     ramos principais (PMC, MVA, Normal) — valores batem com o cálculo manual, inclusive o
     caminho mais complexo (PMC + Crédito Outorgado com MAX/cap de CALC.1×CALC.2)
   - Integrado em `pages/1_Importar_NF_e.py`: ao processar XMLs, persiste os itens e regenera
     a planilha de TODAS as competências tocadas (não só o lote do dia), com botão de download
   - Revisão 2026-06-16: a competência é determinada pelo **nome da pasta importada**
     (`extrair_competencia_pasta()`, exige formato `AAAA-MM`), não pela data de emissão de cada
     nota — comportamento correto confirmado pelo usuário: "todos os xmls contidos na pasta do
     mês entram na planilha do mês", mesmo que uma nota tenha sido emitida no mês anterior. A
     coluna DATA da planilha continua mostrando a data real de emissão (só o agrupamento por
     competência mudou). Pasta sem nome `AAAA-MM` é rejeitada com mensagem clara na tela.
   - Trilha **Ajustada** ainda não implementada (mesma lógica, replicar depois)
   - Revisão 2026-06-16 (2) — **layout de colunas da aba RegimeEspecial corrigido**:
     - Removida a "Coluna2" (antiga AC, sempre vazia, sem uso) — toda a cadeia de cálculo
       deslocou uma posição à esquerda: `AD`=BC ICMS ST APURADO, `AE`=Aliquota Interna,
       `AF`=VLR ICMS ST APURADO, `AG`=Crédito Outorgado devido, `AH`=CALC.1, `AI`=CALC.2,
       `AJ`=CRÉD.OUTORG., `AK`=Valor ICMS a Pagar (era AE-AL antes)
     - **`Y` (PMC) agora é SEMPRE o PMC histórico do produto** — `cmed_comparador.comparar_pmc()`
       não sobrescreve mais `item['pmc']` quando há divergência com a CMED
     - Nova coluna `AN` = PMC pesquisado na CMED (`item['pmc_cmed']`, persistido em
       `nfe_item_apuracao.pmc_cmed`); nova coluna `AO` = `=IF(AN{n}<>Y{n},AN{n}-Y{n},0)`
       (diferença). `AM` ("Coluna3") é preenchimento vazio só para AN/AO caírem nas letras
       exatas pedidas pelo usuário
     - `templates/RegimeEspecialMS_template.xlsm` regenerado; Resumo `C10/C11/C13` (somas por
       coluna) corrigidas para as novas letras — `C14` usa referência estruturada
       (`tabRegEsp[VLR ICMS ST RETIDO]`) e não precisou mudar
     - Tabela "PMC com divergência" em `1_Importar_NF_e.py` agora mostra PMC Histórico/CMED
       direto de `item['pmc']`/`item['pmc_cmed']` (antes reconstruía o histórico subtraindo a
       divergência, porque `pmc` era sobrescrito)

### 🟢 FUTURO
9. **Geração de Planilhas (Ajustada)** — Replicar a geração do item 8 para a trilha Ajustada
10. **Envio por e-mail** — Módulo de envio automático ao setor fiscal
11. **Deploy** — Vercel (frontend) + Supabase (migrar do SQLite para PostgreSQL)

---

## 🛠️ STACK E DEPENDÊNCIAS
- **Python 3.12** (já instalado)
- **pandas 2.3.2** — leitura de Excel
- **openpyxl 3.1.5** — suporte a .xlsx
- **requests 2.32.5** — HTTP requests
- **beautifulsoup4 4.14.3** — web scraping
- **lxml 6.0.2** — parser HTML
- **sqlite3** — incluso no Python, sem instalação

### Para instalar tudo de uma vez:
```bash
pip install pandas openpyxl requests beautifulsoup4 lxml
```

---

## ❓ DÚVIDAS EM ABERTO (Para o operador/usuário)
1. O download automático do CMED falha porque o site usa JavaScript. Preferência: script de scraping avançado (Playwright/Selenium) ou manter como download manual?
2. A classificação entre Positiva/Negativa/Neutra vem do campo "Tipo de Lista" da própria tabela CMED ou tem uma lógica adicional baseada no NCM?
3. Os XMLs das NF-es: serão importados via upload de pasta no navegador ou lidos de um caminho fixo no Windows (ex: `G:\NF-e\`)?
4. O formato do arquivo de envio ao fiscal por e-mail: é o mesmo Excel histórico `Rotili - EnvioFiscal-...` ou pode mudar?

---

## ✅ CONVENÇÕES DO PROJETO
- **Idioma:** Português do Brasil em tudo (comentários, variáveis, mensagens)
- **Organização:** Nada solto na raiz — arquivos MD vão em `docs/`, scripts em `scripts/`, código em `src/`
- **BD:** SQLite local por enquanto, pensado para migrar para PostgreSQL/Supabase depois
- **Git:** Commits no padrão conventional commits (`feat:`, `fix:`, `chore:`, `docs:`)
- **Regra de ouro:** Não altere o que não foi pedido. Preserve lógica existente.
