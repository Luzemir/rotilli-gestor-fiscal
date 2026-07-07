"""
util_extracao.py — Helper de teste: extrai uma função de um arquivo .py via AST.

Necessário porque as páginas Streamlit (src/streamlit/pages/*.py) executam
st.set_page_config etc. no nível de módulo e não podem ser importadas em teste.
A extração via AST compila SOMENTE a função pedida, num namespace controlado —
o que também permite injetar fakes (ex: consultar_pmc_cmed) para os testes de
consistência entre as cópias deliberadas da pré-classificação (ver AGENTS.md).
"""
import ast
import os

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def extrair_funcao(caminho_relativo: str, nome_funcao: str, namespace: dict):
    """
    Compila a função `nome_funcao` do arquivo (relativo à raiz do projeto)
    dentro de `namespace` e a retorna. Levanta AssertionError se não achar.
    """
    caminho = os.path.join(RAIZ, caminho_relativo)
    with open(caminho, encoding='utf-8') as f:
        fonte = f.read()

    arvore = ast.parse(fonte)
    for node in arvore.body:
        if isinstance(node, ast.FunctionDef) and node.name == nome_funcao:
            modulo = ast.Module(body=[node], type_ignores=[])
            codigo = compile(modulo, filename=f'<{caminho_relativo}:{nome_funcao}>', mode='exec')
            exec(codigo, namespace)
            return namespace[nome_funcao]

    raise AssertionError(f'Função {nome_funcao!r} não encontrada em {caminho_relativo}')
