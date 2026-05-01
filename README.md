# Controle de Estoque Pokémon

Sistema completo de gerenciamento de estoque com API backend e frontend interativo.

## 📁 Estrutura do Projeto

```
.
├── backend/                    # Backend FastAPI (refatorado)
│   ├── main.py                # Aplicação principal com rotas
│   ├── models.py              # Modelos Pydantic
│   ├── db.py                  # Operações de banco de dados
│   ├── services.py            # Lógica de negócio e integrações
│   ├── config.py              # Configurações (env loader)
│   ├── requirements.txt        # Dependências Python
│   └── .gitignore             # Git ignore para backend
│
├── frontend/                   # Frontend Next.js + React
│   ├── app/                   # App routes (Páginas)
│   ├── components/            # Componentes React reutilizáveis
│   ├── lib/                   # Utilitários e API client
│   ├── package.json           # Dependências Node
│   └── .gitignore             # Git ignore para frontend
│
├── .gitignore                 # Git ignore global
├── README.md                  # Este arquivo
└── estoque.db                 # Base de dados SQLite
```

## 🚀 Setup

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate  # ou: venv\Scripts\activate (Windows)
pip install -r requirements.txt

# Configurar .env
echo "POKEWALLET_API_KEY=sua_chave_aqui" > .env

# Rodar servidor
python -m uvicorn main:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Acesse: http://localhost:3000 | API: http://localhost:8000

## 🏗️ Arquitetura Backend (Refatorado)

- **main.py**: Rotas e middleware CORS
- **models.py**: Schemas Pydantic (Remessa, Carta, Booster, Pedido)
- **db.py**: Conexão SQLite, inicialização de schema
- **services.py**: Lógica de rateio, integração PokéWallet
- **config.py**: Loader de variáveis de ambiente

## 🔐 Segurança

- `.env` é ignorado pelo Git (proteção de credenciais)
- `node_modules/` e `__pycache__/` não são commitados
- `.gitignore` configurado globalmente e por pasta

## 📊 Tabelas

- **remessas**: Shipments com impostos e frete
- **cartas**: Cards com rateio de custos
- **boosters**: Booster packs com quantidade
- **pedidos**: Unified orders (cartas + boosters)

## ✨ Features

✅ Gestão de remessas, cartas e boosters
✅ Cálculo automático de rateio (proporcional)
✅ Sincronização de status pedido → carta
✅ Integração PokéWallet (imagens fallback)
✅ UI com icon buttons e autocomplete
✅ Confirmação dupla para exclusões
