"""Database operations."""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "estoque.db"


def get_conn() -> sqlite3.Connection:
    """Get SQLite connection with proper config."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    """Convert SQLite row to dict."""
    return dict(row) if row else None


def init_db() -> None:
    """Initialize database schema."""
    conn = get_conn()
    try:
        cursor = conn.cursor()
        
        # Remessas table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS remessas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT UNIQUE NOT NULL,
                valor REAL NOT NULL,
                valor_impostos REAL NOT NULL,
                valor_frete REAL NOT NULL,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Cartas table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cartas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_carta TEXT NOT NULL,
                codigo_carta TEXT NOT NULL,
                colecao_id TEXT NOT NULL,
                preco_custo REAL NOT NULL,
                remessa_id INTEGER NOT NULL,
                preco_venda_minimo REAL NOT NULL,
                imagem_url TEXT,
                preco_remessa REAL NOT NULL DEFAULT 0,
                custo_final REAL NOT NULL DEFAULT 0,
                status TEXT DEFAULT 'em estoque',
                cliente TEXT DEFAULT '',
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (remessa_id) REFERENCES remessas(id) ON DELETE CASCADE
            )
        """)
        
        # Boosters table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS boosters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_colecao TEXT NOT NULL,
                quantidade_booster INTEGER NOT NULL,
                preco_custo REAL NOT NULL,
                remessa_id INTEGER NOT NULL,
                custo_minimo REAL NOT NULL,
                preco_remessa REAL NOT NULL DEFAULT 0,
                custo_final REAL NOT NULL DEFAULT 0,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (remessa_id) REFERENCES remessas(id) ON DELETE CASCADE
            )
        """)
        
        # Pedidos table (unified)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_item TEXT NOT NULL CHECK (tipo_item IN ('carta', 'booster')),
                carta_id INTEGER,
                booster_id INTEGER,
                quantidade INTEGER NOT NULL DEFAULT 1,
                cliente TEXT NOT NULL,
                status TEXT NOT NULL,
                criado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (carta_id) REFERENCES cartas(id) ON DELETE CASCADE,
                FOREIGN KEY (booster_id) REFERENCES boosters(id) ON DELETE CASCADE
            )
        """)
        
        conn.commit()
    finally:
        conn.close()
