# Project.md (Decision Log) - Rotilli Gestor Fiscal

## Objetivo e Escopo
Automatizar o cálculo do ICMS Substituição Tributária com base no Crédito Outorgado (Acordo Rotilli x Sefaz). 
O sistema substituirá as macros de Excel (.xlsm) atuais por uma aplicação robusta, que importa notas fiscais (XML), processa a tabela da Anvisa (CEMED), aplica regras de negócio baseadas em EAN/NCM e gera relatórios (Original e Ajustado).

## Fluxo Principal (Rota de Processamento)

1. **Carga Inicial (One-time):**
   - Criação do Banco de Dados (BD) de Produtos a partir do histórico já classificado nas planilhas (meses 06/2025 a 04/2026), focando na `tabela de produtos.xlsx`.
   - Este DB conterá as listas (Positiva/Negativa/Neutra) e regras já definidas.

2. **Rotina Mensal (Automação):**
   - **Download/Importação dos XMLs:** O usuário faz o input dos XMLs no sistema.
   - **Verificação Primária:** O sistema analisa cada item da NFe buscando no BD de Produtos (via EAN/NCM).
   - **Produto Novo:** Se não for encontrado, o sistema alerta o operador visualmente para que a classificação seja feita antes do fechamento.
   - **Produto Existente e PMC:** Se o produto já existe e é da categoria PMC (0), o sistema consulta a tabela CEMED atual do mês. Se o valor PMC for diferente do cadastro, o sistema atualiza o PMC para o cálculo atual. Caso contrário, mantém o valor.
   - **Geração:** O sistema aplica os cálculos (MVA/Normal/etc) e gera as planilhas/apurações (Original e Ajustada).

## Arquitetura e Stack Tecnológica

- **Frontend / Interface:** Web App moderno utilizando **Next.js (React)** com **Tailwind CSS**.
- **Backend / Processamento:** **Node.js** (integrado ao Next.js).
- **Banco de Dados:** **PostgreSQL** via **Supabase** (para garantir que a "tabela de produtos" fique consolidada e imutável/segura) ou local.
- **Deploy/Hospedagem:** **Vercel** (para o Web App) e Supabase (para o Banco).

## Estrutura de Pastas
```text
/
├── .agent/              # Diretório das skills (Bloqueado no .gitignore)
├── .github/             # Actions e fluxos de CI/CD
├── docs/                # Arquivos Markdown (.md), manuais e logs de decisão
├── scripts/             # Scripts de carga (ex: inicialização da tabela de produtos)
├── src/                 # Código-fonte principal
│   ├── app/             # Rotas da interface (Frontend)
│   ├── components/      # Componentes (UI)
│   ├── core/            # Lógica de negócio, leitura de XML e validação de BD
│   ├── db/              # Esquemas e acesso a dados
│   └── tests/           # Testes
├── assets/              # Imagens e ícones
├── data/                # XMLs temporários e CEMED (Bloqueado no .gitignore)
└── documentos/          # Documentação legado e negócio já existente
```
