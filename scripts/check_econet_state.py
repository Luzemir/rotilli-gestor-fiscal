"""
check_econet_state.py — Verifica o estado do Chrome via CDP e imprime JSON.

Saída (stdout): JSON com os campos:
  conectado      (bool) — Chrome responde na porta 9222
  logado         (bool) — usuário está logado no Econet
  pagina_correta (bool) — aba atual está na página de Substituição Tributária
  url            (str)  — URL da aba ativa do Econet
  erro           (str)  — mensagem de erro, se houver

Chamado pelo Streamlit via subprocess.run(..., capture_output=True).
"""
import json
import sys

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print(json.dumps({
        'conectado': False, 'logado': False, 'pagina_correta': False,
        'url': '', 'erro': 'Playwright não instalado. Execute: pip install playwright && playwright install chromium',
    }))
    sys.exit(0)

CDP_URL     = 'http://127.0.0.1:9222'
ECONET_HOST = 'econeteditora.com.br'


def _conta_seguro(locator) -> int:
    try:
        return locator.count()
    except Exception:
        return 0


def main():
    estado = {
        'conectado':      False,
        'logado':         False,
        'pagina_correta': False,
        'url':            '',
        'erro':           '',
    }

    try:
        with sync_playwright() as pw:
            # ── Tenta conectar ao Chrome ───────────────────────────────────
            try:
                browser = pw.chromium.connect_over_cdp(CDP_URL, timeout=4_000)
            except Exception as e:
                estado['erro'] = f'Chrome não encontrado na porta 9222 ({e})'
                print(json.dumps(estado))
                return

            contextos = browser.contexts
            if not contextos:
                estado['erro'] = 'Nenhum contexto de navegação aberto.'
                print(json.dumps(estado))
                return

            # Pega todas as abas abertas
            paginas = contextos[0].pages
            if not paginas:
                estado['erro'] = 'Nenhuma aba aberta no Chrome.'
                print(json.dumps(estado))
                return

            estado['conectado'] = True

            # ── Encontra a aba do Econet ───────────────────────────────────
            pag = next(
                (p for p in paginas if ECONET_HOST in p.url),
                paginas[0],  # fallback: primeira aba
            )
            estado['url'] = pag.url

            if ECONET_HOST not in pag.url:
                estado['erro'] = f'Nenhuma aba aberta no Econet (URL atual: {pag.url[:60]})'
                print(json.dumps(estado))
                return

            # ── Detecta login ─────────────────────────────────────────────
            # Indicador negativo: campo de senha visível → não logado
            n_senha = _conta_seguro(pag.locator('input[type="password"]:visible'))
            if n_senha > 0:
                estado['logado'] = False
            else:
                # No Econet, se o usuário está logado, a área de conteúdo é acessível.
                # Checamos a ausência de campo de senha como proxy de login.
                estado['logado'] = True

            # ── Detecta página de Substituição Tributária ─────────────────
            # O Econet pode carregar conteúdo em iframes — varredura em todos os frames.
            _termos = ['substituição tributária', 'substituicao tributaria',
                       'lista st', 'icms st', 'icms-st', 'substituição']
            _url_keywords = ['substituicao', 'substitui', 'icms-st', 'lista-st', '/st/']

            _todos_frames = pag.frames  # inclui main frame + sub-frames
            n_estado = n_ncm = n_texto = n_url = 0
            _frames_urls: list[str] = []

            for _fr in _todos_frames:
                _fu = _fr.url.lower()
                _frames_urls.append(_fr.url[:80])

                # URL do frame
                if not n_url and any(k in _fu for k in _url_keywords):
                    n_url = 1

                # Texto do body do frame
                if not n_texto:
                    try:
                        _ft = (_fr.locator('body').inner_text(timeout=2_000) or '').lower()
                        if any(t in _ft for t in _termos):
                            n_texto = 1
                    except Exception:
                        pass

                # Inputs relacionados ao estado
                if not n_estado:
                    for _s in ('[placeholder*="Estado"]', '[placeholder*="estado"]',
                               'select option[value="MS"]', '[aria-label*="Estado"]'):
                        try:
                            if _fr.locator(_s).count() > 0:
                                n_estado = 1
                                break
                        except Exception:
                            pass

                # Campo de busca por NCM
                if not n_ncm:
                    for _s in ('[placeholder*="NCM"]', '[placeholder*="ncm"]',
                               '[placeholder*="código"]', '[placeholder*="Pesquisar"]'):
                        try:
                            if _fr.locator(_s).count() > 0:
                                n_ncm = 1
                                break
                        except Exception:
                            pass

            estado['pagina_correta'] = (n_estado + n_ncm + n_texto + n_url) >= 1
            estado['_dbg'] = (
                f'estado={n_estado} ncm={n_ncm} texto={n_texto} url={n_url} '
                f'frames={len(_todos_frames)} main_url={pag.url[:60]}'
            )

    except Exception as e:
        estado['erro'] = str(e)

    print(json.dumps(estado))


if __name__ == '__main__':
    main()
