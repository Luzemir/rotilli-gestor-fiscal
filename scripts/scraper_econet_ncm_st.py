"""
scraper_econet_ncm_st.py — Raspagem híbrida do portal Econet para atualizar ncm_st

FLUXO:
  1. Operador abre o Chrome com porta de debug, faz login e resolve captcha.
  2. Operador navega até a página de Substituição Tributária no Econet.
  3. Executa este script — ele assume a sessão e varre todos os NCMs pendentes.

COMO USAR:
  Passo 1 — abrir Chrome com debug (executar launch_chrome_debug.bat ou):
    chrome.exe --remote-debugging-port=9222 --user-data-dir="%TEMP%\\ChromeDebugEconet"

  Passo 2 — instalar dependência (uma vez):
    pip install playwright
    playwright install chromium

  Passo 3 — executar o scraper:
    cd c:/APP/Rotilli_GestorFIscal
    python scripts/scraper_econet_ncm_st.py

  Para raspar somente NCMs específicos:
    python scripts/scraper_econet_ncm_st.py --ncm 3004 21069030

  Para re-raspar tudo (ignorar scraped_em):
    python scripts/scraper_econet_ncm_st.py --forcar
"""

import argparse
import asyncio
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime

# ─── Playwright ───────────────────────────────────────────────────────────────
try:
    from playwright.async_api import (
        async_playwright,
        Browser,
        BrowserContext,
        Page,
        TimeoutError as PWTimeout,
    )
except ImportError:
    print("Erro: Playwright não instalado. Execute: pip install playwright && playwright install chromium")
    sys.exit(1)

# ─── Caminhos ─────────────────────────────────────────────────────────────────
ROOT    = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
DB_PATH = os.path.join(ROOT, 'src', 'db', 'gestor_fiscal.db')
LOG_DIR = os.path.join(ROOT, 'logs')

# ─── Configuração da sessão ────────────────────────────────────────────────────
CDP_URL      = 'http://127.0.0.1:9222'   # IPv4 explícito — evita resolução IPv6 no Windows
ESTADO_ALVO  = 'MS'
TIMEOUT_MS   = 20_000                   # timeout geral para AJAX (milissegundos)
TIMEOUT_FAST = 5_000                    # timeout para elementos que devem carregar rápido
RETRY_MAX    = 3                        # tentativas por CEST antes de desistir

# ─── Seletores ────────────────────────────────────────────────────────────────
# Ajuste estes seletores se o Econet atualizar o layout do portal.
# Estratégia de prioridade: placeholder > aria-label > role+text > CSS > XPath
SEL = {
    # Página de pesquisa (Imagem 1/2)
    'dropdown_estado':   '[placeholder="Selecione Estados"], [aria-label*="Estado"]',
    'opcao_estado':      'li:has-text("{estado}"), [role="option"]:has-text("{estado}")',
    'dropdown_tipo':     'text=NCM',          # seletor do dropdown de tipo de busca
    'campo_ncm':         '[placeholder="Pesquisar por código NCM"]',
    'botao_buscar':      'button[type="submit"], button:has(.fa-search), button:has(svg)',
    'sentinela_result':  'text=Resultado para busca',  # aparece quando resultados carregam
    'linhas_resultado':  'table tbody tr:has(td)',

    # Coluna CEST na linha de resultado (Imagem 2)
    'cel_ncm_linha':     'td:nth-child(1)',
    'cel_cest_linha':    'td:nth-child(2)',
    'cel_segmento':      'td:nth-child(3)',

    # Página de detalhe (Imagem 3)
    'aba_icms_st':       'button:has-text("ICMS-ST"), a:has-text("ICMS-ST")',
    'linha_estado_ms':   'tr:has(td:text-is("MS")):not(:has([class*="header"]))',
    'botao_voltar':      'button:has-text("Voltar"), a:has(.fa-arrow-left), [aria-label*="Voltar"], svg[data-icon="arrow-left"]',

    # Tabela expandida de MVAs (Imagem 4)
    'sentinela_mva':     'text=Tipo de Cálculo',
    'tabela_mva':        'table:has(th:text-is("Original")), table:has(td:has-text("MVA"))',
    'linha_mva':         'tr:has(td:has-text("MVA"))',
    'aliquota_interna':  'td:nth-child(4)',   # coluna Alíquota Interna na linha MS
    'base_legal':        'a[href*="RICMS"], td:has-text("RICMS/MS")',
    'segmento_detalhe':  'td:last-child',    # última célula da linha Base Legal/Segmento
}

# ─── Logging ──────────────────────────────────────────────────────────────────
os.makedirs(LOG_DIR, exist_ok=True)
_log_file = os.path.join(LOG_DIR, f'scraper_econet_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(_log_file, encoding='utf-8'),
    ],
)
log = logging.getLogger('scraper_econet')


# ═══════════════════════════════════════════════════════════════════════════════
# BANCO DE DADOS
# ═══════════════════════════════════════════════════════════════════════════════

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _migrar_schema(conn: sqlite3.Connection):
    """Adiciona colunas necessárias ao schema se ainda não existirem."""
    for col, tipo in [('aliquota_interna', 'REAL'), ('scraped_em', 'TEXT')]:
        try:
            conn.execute(f'ALTER TABLE ncm_st ADD COLUMN {col} {tipo}')
            conn.commit()
            log.info(f'Coluna adicionada ao schema: {col} {tipo}')
        except Exception:
            pass  # coluna já existe


def get_ncms_pendentes(conn: sqlite3.Connection, forcar: bool = False) -> list[str]:
    """
    Retorna NCMs distintos da tabela ncm_st que ainda precisam ser raspados.
    forcar=True ignora scraped_em e retorna todos.
    """
    if forcar:
        sql = "SELECT DISTINCT ncm FROM ncm_st ORDER BY ncm"
    else:
        sql = "SELECT DISTINCT ncm FROM ncm_st WHERE scraped_em IS NULL ORDER BY ncm"
    return [r['ncm'] for r in conn.execute(sql).fetchall()]


def get_cests_do_ncm(conn: sqlite3.Connection, ncm: str) -> list[dict]:
    """Retorna todas as linhas (id, cest, cest_norm) de um NCM específico."""
    rows = conn.execute(
        "SELECT id, cest, cest_norm FROM ncm_st WHERE ncm = ?", (ncm,)
    ).fetchall()
    return [dict(r) for r in rows]


def salvar_dados_cest(conn: sqlite3.Connection, cest_norm: str, dados: dict) -> bool:
    """Atualiza os campos raspados para o CEST correspondente. Retorna True se atualizou."""
    cur = conn.execute(
        '''UPDATE ncm_st SET
            mva_interno       = COALESCE(?, mva_interno),
            mva_aliq4         = COALESCE(?, mva_aliq4),
            mva_aliq7         = COALESCE(?, mva_aliq7),
            mva_aliq12        = COALESCE(?, mva_aliq12),
            descricao         = COALESCE(?, descricao),
            dispositivo_legal = COALESCE(?, dispositivo_legal),
            aliquota_interna  = COALESCE(?, aliquota_interna),
            scraped_em        = ?
           WHERE cest_norm = ?''',
        (
            dados.get('mva_interno'),
            dados.get('mva_aliq4'),
            dados.get('mva_aliq7'),
            dados.get('mva_aliq12'),
            dados.get('descricao'),
            dados.get('dispositivo_legal'),
            dados.get('aliquota_interna'),
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            cest_norm,
        ),
    )
    conn.commit()
    return cur.rowcount > 0


def marcar_ncm_sem_resultado(conn: sqlite3.Connection, ncm: str):
    """Marca todas as linhas do NCM como verificadas, sem dados Econet."""
    conn.execute(
        "UPDATE ncm_st SET scraped_em = ? WHERE ncm = ? AND scraped_em IS NULL",
        (datetime.now().strftime('%Y-%m-%d %H:%M:%S') + ' [SEM_RESULTADO]', ncm),
    )
    conn.commit()


# ═══════════════════════════════════════════════════════════════════════════════
# PARSERS
# ═══════════════════════════════════════════════════════════════════════════════

def _parse_pct(texto: str | None) -> float | None:
    """Converte '24,41%' → 24.41 (float, sem /100). Retorna None se não parsear."""
    if not texto:
        return None
    limpo = texto.replace('%', '').replace(',', '.').strip()
    try:
        v = float(limpo)
        return v if v > 0 else None
    except ValueError:
        return None


def _norm_cest(cest: str) -> str:
    return re.sub(r'[.\s-]', '', cest).strip()


def _formatar_ncm_busca(ncm: str) -> str:
    """
    Garante que o NCM está em formato pontilhado para a busca Econet.
    Ex: '30049099' → '3004.90.99', '3004' → '3004'
    """
    n = re.sub(r'[.\s]', '', str(ncm))
    if len(n) == 8:
        return f'{n[:4]}.{n[4:6]}.{n[6:]}'
    if len(n) == 6:
        return f'{n[:4]}.{n[4:6]}'
    return ncm  # retorna como está se não bater com padrão conhecido


# ═══════════════════════════════════════════════════════════════════════════════
# INTERAÇÕES COM A PÁGINA
# ═══════════════════════════════════════════════════════════════════════════════

async def _safe_text(locator, default: str = '') -> str:
    try:
        return (await locator.first.inner_text(timeout=TIMEOUT_FAST)).strip()
    except Exception:
        return default


async def _selecionar_estado(page: Page, estado: str = 'MS'):
    """Seleciona o estado no dropdown customizado 'Selecione Estados'."""
    log.info(f'  Selecionando estado: {estado}')
    try:
        dropdown = page.locator(SEL['dropdown_estado']).first
        await dropdown.click(timeout=TIMEOUT_FAST)
        await page.wait_for_timeout(400)

        # Tenta digitar para filtrar
        await dropdown.fill(estado)
        await page.wait_for_timeout(300)

        # Clica na opção correspondente na lista expandida
        sel_opcao = SEL['opcao_estado'].format(estado=estado)
        opcao = page.locator(sel_opcao).first
        await opcao.click(timeout=TIMEOUT_FAST)
        await page.wait_for_timeout(500)
        log.info(f'  Estado {estado} selecionado.')
    except PWTimeout:
        log.warning('  Timeout ao selecionar estado — talvez já esteja selecionado.')


async def _buscar_ncm(page: Page, ncm: str):
    """Preenche o campo de NCM, limpa o anterior e clica em buscar."""
    ncm_fmt = _formatar_ncm_busca(ncm)
    log.info(f'  Buscando NCM: {ncm_fmt}')

    campo = page.locator(SEL['campo_ncm']).first
    await campo.click(timeout=TIMEOUT_FAST)
    await campo.triple_click()          # seleciona tudo
    await campo.fill(ncm_fmt)
    await page.wait_for_timeout(300)

    # Clica no botão de busca
    botao = page.locator(SEL['botao_buscar']).first
    await botao.click(timeout=TIMEOUT_FAST)


async def _aguardar_resultados(page: Page) -> bool:
    """Espera a tabela de resultados ou mensagem 'sem resultado'. Retorna True se há resultados."""
    try:
        # Espera qualquer um dos dois: resultados ou "nenhum resultado"
        await page.wait_for_selector(
            f'{SEL["sentinela_result"]}, text=Nenhum resultado, text=nenhum resultado encontrado',
            timeout=TIMEOUT_MS,
        )
        sem_resultado = await page.locator('text=Nenhum resultado, text=nenhum resultado encontrado').count()
        return sem_resultado == 0
    except PWTimeout:
        log.warning('  Timeout aguardando resultados da busca.')
        return False


async def _coletar_hrefs_resultado(page: Page) -> list[tuple[str, str]]:
    """
    Coleta todos os pares (cest_texto, href_detalhe) da lista de resultados.
    Estratégia dupla:
      1. Href direto no <a> da linha  — navegação sem reconstruir DOM
      2. Sem href (onclick JS)        — guarda '' e clicaremos por índice
    """
    pares: list[tuple[str, str]] = []
    linhas = await page.locator(SEL['linhas_resultado']).all()

    for linha in linhas:
        try:
            cest_txt = await _safe_text(linha.locator(SEL['cel_cest_linha']))
            if not cest_txt:
                continue
            link = linha.locator('a[href]').first
            href = await link.get_attribute('href', timeout=TIMEOUT_FAST) if await link.count() else None
            pares.append((cest_txt, href or ''))
        except Exception:
            continue

    log.info(f'  {len(pares)} resultado(s) coletado(s).')
    return pares


async def _navegar_para_detalhe(page: Page, href: str | None, indice: int = 0):
    """
    Navega para a página de detalhe.
    - Com href: goto direto (mais confiável, DOM da lista não importa).
    - Sem href: clica na linha pelo índice (onclick JS no Econet).
    """
    if href:
        url = href if href.startswith('http') else f'https://www.econeteditora.com.br{href}'
        await page.goto(url, wait_until='domcontentloaded', timeout=TIMEOUT_MS)
    else:
        # Fallback: re-localiza a linha pelo índice e clica
        linha = page.locator(SEL['linhas_resultado']).nth(indice)
        await linha.click(timeout=TIMEOUT_FAST)
        await page.wait_for_load_state('domcontentloaded', timeout=TIMEOUT_MS)


async def _ativar_aba_icms_st(page: Page):
    """Garante que a aba ICMS-ST está ativa na página de detalhe."""
    try:
        aba = page.locator(SEL['aba_icms_st']).first
        if await aba.count():
            await aba.click(timeout=TIMEOUT_FAST)
            await page.wait_for_timeout(600)
    except Exception:
        pass


async def _expandir_linha_ms(page: Page) -> bool:
    """
    Localiza a linha do estado MS na tabela ICMS-ST e clica para expandir.
    Retorna True se expandiu com sucesso.
    """
    try:
        linha_ms = page.locator(SEL['linha_estado_ms']).first
        if not await linha_ms.is_visible(timeout=TIMEOUT_FAST):
            return False

        # Captura alíquota interna antes de expandir (está na linha de resumo)
        # (guardada para uso posterior em _extrair_mvas)
        await linha_ms.click(timeout=TIMEOUT_FAST)

        # Espera o conteúdo expandido carregar
        await page.wait_for_selector(SEL['sentinela_mva'], timeout=TIMEOUT_MS)
        return True
    except PWTimeout:
        return False
    except Exception as e:
        log.debug(f'  _expandir_linha_ms: {e}')
        return False


async def _extrair_aliquota_interna(page: Page) -> float | None:
    """
    Lê a alíquota interna da linha MS (antes do expand).
    Não assume posição fixa — procura a primeira célula com padrão 'N%'.
    """
    try:
        linha_ms = page.locator(SEL['linha_estado_ms']).first
        celulas  = await linha_ms.locator('td').all()
        for celula in celulas:
            txt = await _safe_text(celula)
            # Célula de alíquota: número seguido de '%', ex: '17%' ou '17,0%'
            if '%' in txt and re.match(r'^\d', txt.strip()):
                return _parse_pct(txt)
        return None
    except Exception:
        return None


async def _extrair_mvas(page: Page, aliquota_interna: float | None) -> dict | None:
    """
    Lê a tabela de MVAs e campos complementares após a linha MS ser expandida.
    Estrutura esperada (Imagem 4):
      Tipo de Cálculo | Original | Ajustada 4% | Ajustada 7% | Ajustada 12%
    """
    dados: dict = {'aliquota_interna': aliquota_interna}

    try:
        tabela = page.locator(SEL['tabela_mva']).first
        await tabela.wait_for(timeout=TIMEOUT_MS)

        # Linha "MVA" na tabela expandida
        linha_mva = tabela.locator(SEL['linha_mva']).first
        celulas   = await linha_mva.locator('td').all()

        if len(celulas) >= 2:
            dados['mva_interno'] = _parse_pct(await _safe_text(celulas[1]))
        if len(celulas) >= 3:
            dados['mva_aliq4']   = _parse_pct(await _safe_text(celulas[2]))
        if len(celulas) >= 4:
            dados['mva_aliq7']   = _parse_pct(await _safe_text(celulas[3]))
        if len(celulas) >= 5:
            dados['mva_aliq12']  = _parse_pct(await _safe_text(celulas[4]))

        # Base legal (link RICMS/MS)
        base_el = page.locator(SEL['base_legal']).first
        if await base_el.count():
            dados['dispositivo_legal'] = await _safe_text(base_el)

        # Segmento (texto descritivo ao lado da base legal)
        segmento_el = page.locator(f'{SEL["base_legal"]} ~ td, td:has-text("farmac"), td:has-text("Medicamento")').first
        if await segmento_el.count():
            dados['descricao'] = await _safe_text(segmento_el)

        return dados if any(v is not None for k, v in dados.items() if k != 'aliquota_interna') else None

    except PWTimeout:
        log.warning('  Timeout ao ler tabela de MVAs.')
        return None
    except Exception as e:
        log.error(f'  Erro ao extrair MVAs: {e}')
        return None


async def _voltar_para_lista(page: Page):
    """Volta para a lista de resultados após processar um detalhe."""
    try:
        botao = page.locator(SEL['botao_voltar']).first
        if await botao.count():
            await botao.click(timeout=TIMEOUT_FAST)
        else:
            await page.go_back()
        await page.wait_for_selector(SEL['sentinela_result'], timeout=TIMEOUT_MS)
        await page.wait_for_timeout(500)
    except Exception:
        await page.go_back()
        await page.wait_for_timeout(1000)


# ═══════════════════════════════════════════════════════════════════════════════
# LOOP PRINCIPAL
# ═══════════════════════════════════════════════════════════════════════════════

async def processar_cest(page: Page, conn: sqlite3.Connection, cest_txt: str, href: str, indice: int = 0) -> bool:
    """
    Navega para o detalhe de um CEST, extrai dados MS e salva no DB.
    Retorna True se dados foram salvos com sucesso.
    """
    cest_norm = _norm_cest(cest_txt)

    for tentativa in range(1, RETRY_MAX + 1):
        try:
            await _navegar_para_detalhe(page, href, indice)
            await _ativar_aba_icms_st(page)

            # Lê alíquota interna ANTES de expandir
            aliq = await _extrair_aliquota_interna(page)

            expandiu = await _expandir_linha_ms(page)
            if not expandiu:
                log.warning(f'    Estado MS não encontrado para CEST {cest_txt}.')
                return False

            dados = await _extrair_mvas(page, aliq)
            if not dados:
                log.warning(f'    Dados não extraídos para CEST {cest_txt} (tentativa {tentativa}).')
                if tentativa < RETRY_MAX:
                    await page.wait_for_timeout(2000)
                    continue
                return False

            atualizado = salvar_dados_cest(conn, cest_norm, dados)
            if atualizado:
                log.info(
                    f'    ✓ CEST {cest_txt} | Alíq.Int: {aliq}% '
                    f'| MVA: {dados.get("mva_interno")}% '
                    f'| Ajust.4%: {dados.get("mva_aliq4")}% '
                    f'| Ajust.7%: {dados.get("mva_aliq7")}% '
                    f'| Ajust.12%: {dados.get("mva_aliq12")}%'
                )
            else:
                log.warning(f'    CEST {cest_norm} não encontrado no banco — linha não atualizada.')

            return True

        except PWTimeout:
            log.warning(f'    Timeout ao processar CEST {cest_txt} (tentativa {tentativa}).')
            if tentativa < RETRY_MAX:
                await page.wait_for_timeout(2000)
        except Exception as e:
            log.error(f'    Erro inesperado no CEST {cest_txt}: {e}')
            break

    return False


async def processar_ncm(page: Page, conn: sqlite3.Connection, ncm: str):
    """Busca um NCM no Econet, itera sobre todos os CESTs e salva os dados."""
    log.info(f'┌── NCM: {ncm}')

    await _buscar_ncm(page, ncm)
    tem_resultados = await _aguardar_resultados(page)

    if not tem_resultados:
        log.info(f'└── Nenhum resultado para NCM {ncm}. Marcando como processado.')
        marcar_ncm_sem_resultado(conn, ncm)
        return

    # Coleta todos os pares (cest, href) antes de navegar — evita re-scrape de DOM
    pares = await _coletar_hrefs_resultado(page)
    if not pares:
        log.info(f'└── Lista de resultados vazia para NCM {ncm}.')
        marcar_ncm_sem_resultado(conn, ncm)
        return

    ok = 0
    for idx, (cest_txt, href) in enumerate(pares, 1):
        log.info(f'│   [{idx}/{len(pares)}] CEST: {cest_txt}')
        # Passa o índice (base-0) para o fallback de click quando não há href
        sucesso = await processar_cest(page, conn, cest_txt, href, indice=idx - 1)
        if sucesso:
            ok += 1
        # Volta para a lista após cada detalhe
        await _voltar_para_lista(page)

    log.info(f'└── NCM {ncm} concluído: {ok}/{len(pares)} CEST(s) atualizados.')


async def main(ncms_cli: list[str] | None, forcar: bool):
    conn = get_conn()
    _migrar_schema(conn)

    if ncms_cli:
        ncms = ncms_cli
        log.info(f'Modo manual: {len(ncms)} NCM(s) informado(s) via CLI.')
    else:
        ncms = get_ncms_pendentes(conn, forcar=forcar)

    if not ncms:
        log.info('Nenhum NCM pendente. Use --forcar para re-raspar tudo.')
        conn.close()
        return

    log.info(f'Total de NCMs a processar: {len(ncms)}')
    log.info(f'NCMs: {ncms}')

    async with async_playwright() as pw:
        # ── Conecta ao Chrome existente via CDP ───────────────────────────────
        try:
            browser: Browser = await pw.chromium.connect_over_cdp(CDP_URL)
            log.info(f'Conectado ao Chrome via CDP em {CDP_URL}.')
        except Exception as e:
            log.error(
                f'Não foi possível conectar ao Chrome em {CDP_URL}.\n'
                f'  Verifique se o Chrome foi aberto com:\n'
                f'  chrome.exe --remote-debugging-port=9222\n'
                f'  Erro: {e}'
            )
            conn.close()
            return

        context: BrowserContext = browser.contexts[0]
        page: Page = context.pages[0] if context.pages else await context.new_page()

        # Verifica se está no Econet
        url_atual = page.url
        if 'econeteditora' not in url_atual:
            log.error(
                f'O Chrome não está na página do Econet.\n'
                f'  URL atual: {url_atual}\n'
                f'  Navegue até a Substituição Tributária antes de executar o script.'
            )
            conn.close()
            return

        log.info(f'Página atual: {url_atual}')

        # Garante que MS está selecionado no dropdown de estado
        await _selecionar_estado(page, ESTADO_ALVO)

        # ── Processa cada NCM ─────────────────────────────────────────────────
        total = len(ncms)
        for i, ncm in enumerate(ncms, 1):
            log.info(f'═══ ({i}/{total}) ═══')
            await processar_ncm(page, conn, ncm)

    conn.close()

    # ── Relatório final ───────────────────────────────────────────────────────
    print()
    print('=' * 60)
    print('  ✅  Processo de atualização concluído com sucesso!')
    print(f'  📋  Log salvo em: {_log_file}')
    print('=' * 60)

    # Sumário do banco
    conn2 = get_conn()
    total_db    = conn2.execute('SELECT COUNT(*) FROM ncm_st').fetchone()[0]
    atualizados = conn2.execute("SELECT COUNT(*) FROM ncm_st WHERE scraped_em IS NOT NULL AND scraped_em NOT LIKE '%SEM_RESULTADO%'").fetchone()[0]
    sem_result  = conn2.execute("SELECT COUNT(*) FROM ncm_st WHERE scraped_em LIKE '%SEM_RESULTADO%'").fetchone()[0]
    pendentes   = conn2.execute('SELECT COUNT(*) FROM ncm_st WHERE scraped_em IS NULL').fetchone()[0]
    conn2.close()

    print(f'  Total na tabela:   {total_db}')
    print(f'  Atualizados:       {atualizados}')
    print(f'  Sem resultado:     {sem_result}')
    print(f'  Ainda pendentes:   {pendentes}')
    print('=' * 60)


# ─── Ponto de entrada ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Scraper Econet → ncm_st')
    parser.add_argument(
        '--ncm', nargs='+', metavar='NCM',
        help='Processar apenas os NCMs informados (ex: --ncm 3004 21069030)'
    )
    parser.add_argument(
        '--forcar', action='store_true',
        help='Re-raspar mesmo NCMs já processados (ignora scraped_em)'
    )
    args = parser.parse_args()
    asyncio.run(main(ncms_cli=args.ncm, forcar=args.forcar))
