"""
app.py — API REST do Gestor Fiscal Rotilli

Endpoints:
  GET  /api/status              Saúde do sistema e estatísticas do banco
  POST /api/import/nfe          Processa XMLs de NF-e de uma pasta
  POST /api/import/cmed         Processa arquivo(s) CMED de uma pasta
  GET  /api/produtos            Lista produtos cadastrados (paginado, com busca)
  GET  /api/alertas             Lista produtos novos aguardando classificação
  PATCH /api/alertas/{id}       Atualiza status de um alerta

Uso:
  python src/api/app.py
  Acesse: http://localhost:8000/docs  (Swagger UI automático)
"""

import os
import sys
import glob
import sqlite3
from contextlib import contextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Garante que os módulos do projeto são encontrados a partir de qualquer CWD
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.insert(0, os.path.join(ROOT, 'src', 'core'))
sys.path.insert(0, os.path.join(ROOT, 'scripts'))
os.chdir(ROOT)

from nfe_parser import parsear_xml, classificar_itens, _extrair_mes_ano, PMC_DIVERGENTE
from cmed_downloader import processar_arquivo_cmed, init_cmed_db

DB_PATH = os.path.join(ROOT, 'src', 'db', 'gestor_fiscal.db')

app = FastAPI(
    title='Gestor Fiscal Rotilli',
    description='API de automação do ICMS-ST — importação de NF-e, CMED e apuração mensal.',
    version='0.1.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


# ─── Banco de Dados ────────────────────────────────────────────────────────────

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.execute('''
            CREATE TABLE IF NOT EXISTS produto_alerta (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                cnpj_emitente TEXT NOT NULL,
                cod_produto   TEXT NOT NULL,
                ean           TEXT,
                descricao     TEXT,
                num_nf        TEXT,
                data_emissao  TEXT,
                criado_em     TEXT DEFAULT CURRENT_TIMESTAMP,
                status        TEXT DEFAULT 'PENDENTE',
                UNIQUE(cnpj_emitente, cod_produto)
            )
        ''')


@app.on_event('startup')
def startup():
    init_db()


# ─── Modelos de Request ────────────────────────────────────────────────────────

class ImportNFeRequest(BaseModel):
    pasta: str

class ImportCmedRequest(BaseModel):
    pasta: str = os.path.join('Documentos', 'CMED')
    todos: bool = False

class AtualizarAlertaRequest(BaseModel):
    status: str  # PENDENTE | CLASSIFICADO | IGNORADO


# ─── Endpoints ────────────────────────────────────────────────────────────────

@app.get('/api/status', summary='Saúde do sistema e estatísticas do banco')
def status():
    with get_conn() as conn:
        cur = conn.cursor()
        produtos = cur.execute('SELECT COUNT(*) FROM produtos').fetchone()[0]
        competencias = cur.execute('SELECT COUNT(*) FROM produto_competencia').fetchone()[0]
        cmed = cur.execute(
            'SELECT COUNT(*), MIN(mes_ano), MAX(mes_ano) FROM cmed_historico'
        ).fetchone()
        alertas = cur.execute(
            "SELECT COUNT(*) FROM produto_alerta WHERE status = 'PENDENTE'"
        ).fetchone()[0]

    return {
        'status': 'ok',
        'banco': {
            'produtos_cadastrados': produtos,
            'registros_competencia': competencias,
            'cmed_registros': cmed[0],
            'cmed_vigencia': f"{cmed[1]} a {cmed[2]}" if cmed[0] > 0 else 'sem dados',
            'alertas_pendentes': alertas,
        },
    }


@app.post('/api/import/nfe', summary='Processa XMLs de NF-e de uma pasta')
def import_nfe(req: ImportNFeRequest):
    pasta = req.pasta
    if not os.path.isabs(pasta):
        pasta = os.path.join(ROOT, pasta)

    if not os.path.exists(pasta):
        raise HTTPException(status_code=400, detail=f'Pasta não encontrada: {pasta}')

    arquivos = glob.glob(os.path.join(pasta, '*.xml'))
    if not arquivos:
        raise HTTPException(status_code=400, detail='Nenhum arquivo XML encontrado na pasta.')

    todos_classificados = []
    todos_novos = []
    erros = []

    with get_conn() as conn:
        for arq in sorted(arquivos):
            nota = parsear_xml(arq)
            if not nota:
                erros.append(os.path.basename(arq))
                continue

            mes_ano = _extrair_mes_ano(nota.get('data_emissao'))
            classificados, novos = classificar_itens(nota['itens'], conn, mes_ano)
            todos_classificados.extend(classificados)
            todos_novos.extend(novos)

            for item in novos:
                try:
                    conn.execute(
                        '''INSERT OR IGNORE INTO produto_alerta
                               (cnpj_emitente, cod_produto, ean, descricao, num_nf, data_emissao)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (item.get('cnpj_emitente'), item.get('cod_produto'),
                         item.get('ean'), item.get('descricao'),
                         item.get('num_nf'), item.get('data_emissao')),
                    )
                except Exception:
                    pass

    pmc_divergentes = [i for i in todos_classificados if i.get('status') == PMC_DIVERGENTE]

    return {
        'arquivos_lidos': len(arquivos),
        'erros_leitura': erros,
        'itens_classificados': len(todos_classificados),
        'novos_produtos_detectados': len(todos_novos),
        'pmc_atualizados_pela_cmed': len(pmc_divergentes),
        'divergencias_pmc': [
            {
                'cod_produto': i.get('cod_produto'),
                'ean': i.get('ean'),
                'descricao': i.get('descricao'),
                'pmc_bd': round(i['pmc'] - i.get('pmc_divergencia', 0), 2),
                'pmc_cmed': i.get('pmc'),
                'diferenca': i.get('pmc_divergencia'),
            }
            for i in pmc_divergentes
        ],
        'novos_produtos': [
            {
                'cnpj_emitente': i.get('cnpj_emitente'),
                'cod_produto': i.get('cod_produto'),
                'ean': i.get('ean'),
                'descricao': i.get('descricao'),
                'num_nf': i.get('num_nf'),
            }
            for i in todos_novos
        ],
    }


@app.post('/api/import/cmed', summary='Processa arquivo(s) CMED de uma pasta')
def import_cmed(req: ImportCmedRequest):
    pasta = req.pasta
    if not os.path.isabs(pasta):
        pasta = os.path.join(ROOT, pasta)

    if not os.path.exists(pasta):
        raise HTTPException(status_code=400, detail=f'Pasta não encontrada: {pasta}')

    arquivos = sorted(glob.glob(os.path.join(pasta, '*.xls*')))
    if not arquivos:
        raise HTTPException(
            status_code=400,
            detail=(
                'Nenhum arquivo CMED (.xlsx/.xls) encontrado. '
                'Baixe em: https://www.gov.br/anvisa/pt-br/assuntos/medicamentos/cmed/precos'
            ),
        )

    if not req.todos:
        arquivos = [max(arquivos, key=os.path.getmtime)]

    resultados = []
    with get_conn() as conn:
        init_cmed_db(conn)
        for arq in arquivos:
            total = processar_arquivo_cmed(arq, conn)
            resultados.append({'arquivo': os.path.basename(arq), 'registros': total})

    return {
        'arquivos_processados': len(arquivos),
        'resultados': resultados,
        'total_registros': sum(r['registros'] for r in resultados),
    }


@app.get('/api/produtos', summary='Lista produtos cadastrados')
def listar_produtos(
    pagina: int = 1,
    por_pagina: int = 50,
    busca: Optional[str] = None,
):
    offset = (pagina - 1) * por_pagina
    with get_conn() as conn:
        cur = conn.cursor()
        if busca:
            like = f'%{busca}%'
            total = cur.execute(
                'SELECT COUNT(*) FROM produtos WHERE descricao_produto LIKE ? OR cod_produto_origem LIKE ?',
                (like, like),
            ).fetchone()[0]
            rows = cur.execute(
                'SELECT cnpj_remetente, cod_produto_origem, descricao_produto, unidade '
                'FROM produtos WHERE descricao_produto LIKE ? OR cod_produto_origem LIKE ? '
                'ORDER BY descricao_produto LIMIT ? OFFSET ?',
                (like, like, por_pagina, offset),
            ).fetchall()
        else:
            total = cur.execute('SELECT COUNT(*) FROM produtos').fetchone()[0]
            rows = cur.execute(
                'SELECT cnpj_remetente, cod_produto_origem, descricao_produto, unidade '
                'FROM produtos ORDER BY descricao_produto LIMIT ? OFFSET ?',
                (por_pagina, offset),
            ).fetchall()

    return {
        'total': total,
        'pagina': pagina,
        'por_pagina': por_pagina,
        'produtos': [dict(r) for r in rows],
    }


@app.get('/api/alertas', summary='Lista produtos novos aguardando classificação')
def listar_alertas(status: str = 'PENDENTE'):
    with get_conn() as conn:
        rows = conn.execute(
            'SELECT id, cnpj_emitente, cod_produto, ean, descricao, num_nf, '
            'data_emissao, criado_em, status '
            'FROM produto_alerta WHERE status = ? ORDER BY criado_em DESC',
            (status,),
        ).fetchall()

    return {
        'total': len(rows),
        'alertas': [dict(r) for r in rows],
    }


@app.patch('/api/alertas/{alerta_id}', summary='Atualiza status de um alerta')
def atualizar_alerta(alerta_id: int, req: AtualizarAlertaRequest):
    status_validos = {'PENDENTE', 'CLASSIFICADO', 'IGNORADO'}
    if req.status not in status_validos:
        raise HTTPException(
            status_code=400,
            detail=f'Status inválido. Use: {", ".join(status_validos)}',
        )
    with get_conn() as conn:
        cur = conn.execute(
            'UPDATE produto_alerta SET status = ? WHERE id = ?', (req.status, alerta_id)
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail=f'Alerta {alerta_id} não encontrado.')

    return {'id': alerta_id, 'status': req.status}


# ─── Entrada ──────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app:app', host='0.0.0.0', port=8000, reload=True,
                app_dir=os.path.dirname(os.path.abspath(__file__)))
