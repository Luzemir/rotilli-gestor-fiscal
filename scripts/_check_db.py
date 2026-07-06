import sqlite3

conn = sqlite3.connect('src/db/gestor_fiscal.db')
c = conn.cursor()

# Limpar registros inválidos (cabeçalhos capturados por engano)
c.execute("DELETE FROM produto_competencia WHERE mod_bc_icms_st = 'MOD BC ICMS ST'")
conn.commit()
print(f'Registros inválidos removidos: {c.rowcount}')

c.execute('SELECT COUNT(*) FROM produto_competencia')
print(f'Total de registros válidos restantes: {c.fetchone()[0]}')

c.execute('SELECT mod_bc_icms_st, COUNT(*) FROM produto_competencia GROUP BY mod_bc_icms_st ORDER BY mod_bc_icms_st')
print('\nDistribuição final por tipo de tributação:')
mapa = {'0': 'PMC', '1': 'Negativo', '2': 'Positivo', '3': 'Neutro', '4': 'MVA', '5': 'Normal'}
for row in c.fetchall():
    nome = mapa.get(str(row[0]), row[0])
    print(f'  Código {row[0]} ({nome}): {row[1]} registros')

conn.close()
print('\nBanco de dados limpo com sucesso!')
