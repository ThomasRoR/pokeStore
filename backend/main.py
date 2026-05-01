import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from urllib import error as url_error
from urllib import parse as url_parse
from urllib import request as url_request
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

DB_PATH = Path(__file__).parent / "estoque.db"
POKEWALLET_BASE_URL = "https://api.pokewallet.io"
StatusCarta = Literal["em estoque", "vendido", "separado", "enviado", "entregue"]
StatusPedido = Literal["vendido", "separado", "enviado", "entregue"]

app = FastAPI(title="Controle de Estoque Pokemon API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def load_env_file() -> None:
    # Try backend/.env first, then project root .env (two levels up when backend is a subfolder)
    candidates = [Path(__file__).parent / ".env", Path(__file__).parent.parent / ".env", Path.cwd() / ".env"]

    env_path = None
    for cand in candidates:
        if cand.exists():
            env_path = cand
            break

    if env_path is None:
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        os.environ[key] = value


load_env_file()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row else None


def normalize_card_code(value: str) -> str:
    return "".join(ch for ch in value.upper().strip() if ch.isalnum())


def normalize_card_number(value: str) -> str:
    head = (value or "").strip().split("/", 1)[0]
    normalized = normalize_card_code(head)
    if normalized.isdigit():
        return str(int(normalized))
    return normalized


def get_pokewallet_key() -> str:
    api_key = os.getenv("POKEWALLET_API_KEY", "").strip()
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="POKEWALLET_API_KEY nao configurada no backend.",
        )
    return api_key


def pokewallet_auth_headers_variants(api_key: str) -> list[dict[str, str]]:
    return [
        {"X-API-Key": api_key},
        {"Authorization": f"Bearer {api_key}"},
    ]


def pokewallet_client_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/147.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    }


def parse_http_error_detail(exc: url_error.HTTPError, fallback: str) -> str:
    detail = fallback
    try:
        body = exc.read().decode("utf-8")
        if body:
            try:
                parsed = json.loads(body)
                detail = (
                    parsed.get("message")
                    or parsed.get("error")
                    or parsed.get("detail")
                    or detail
                )
            except ValueError:
                detail = body.strip() or detail
    except (ValueError, UnicodeDecodeError, OSError):
        pass
    return detail


def pokewallet_json_get(path: str, query: dict[str, str]) -> dict:
    params = url_parse.urlencode(query)
    url = f"{POKEWALLET_BASE_URL}{path}"
    if params:
        url = f"{url}?{params}"

    api_key = get_pokewallet_key()
    last_forbidden_detail = "Pokewallet retornou erro 403."
    for auth_headers in pokewallet_auth_headers_variants(api_key):
        req = url_request.Request(
            url,
            headers={
                **auth_headers,
                **pokewallet_client_headers(),
                "Accept": "application/json",
            },
            method="GET",
        )
        try:
            with url_request.urlopen(req, timeout=12) as resp:
                payload = resp.read().decode("utf-8")
                return json.loads(payload) if payload else {}
        except url_error.HTTPError as exc:
            detail = parse_http_error_detail(exc, f"Pokewallet retornou erro {exc.code}.")
            if exc.code == 403:
                last_forbidden_detail = detail
                continue
            raise HTTPException(status_code=exc.code, detail=detail)
        except url_error.URLError:
            raise HTTPException(status_code=502, detail="Falha ao conectar na Pokewallet.")
    raise HTTPException(status_code=403, detail=last_forbidden_detail)


def pick_pokewallet_card(results: list[dict], colecao_id: str, codigo_carta: str) -> dict | None:
    target_set = normalize_card_code(colecao_id)
    target_code = normalize_card_number(codigo_carta)

    best_set_and_code = None
    best_set_only = None
    best_code_only = None

    for item in results:
        info = item.get("card_info") or {}
        set_code = normalize_card_code(str(info.get("set_code") or ""))
        card_number = normalize_card_number(str(info.get("card_number") or ""))
        matches_set = bool(target_set and set_code and set_code == target_set)
        matches_code = bool(target_code and card_number and card_number == target_code)

        if matches_set and matches_code:
            best_set_and_code = item
            break
        if matches_set and best_set_only is None:
            best_set_only = item
        if matches_code and best_code_only is None:
            best_code_only = item

    return best_set_and_code or best_set_only or best_code_only


def normalize_pokewallet_language(value: str) -> str:
    lang = (value or "").strip().lower()
    aliases = {
        "ja": "jap",
        "jp": "jap",
        "jpn": "jap",
        "japanese": "jap",
        "en": "eng",
        "english": "eng",
    }
    return aliases.get(lang, lang)


def init_db() -> None:
    with closing(get_conn()) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS remessas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                valor_remessa REAL NOT NULL CHECK (valor_remessa >= 0),
                valor_impostos REAL NOT NULL CHECK (valor_impostos >= 0),
                valor_frete REAL NOT NULL CHECK (valor_frete >= 0),
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cartas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_carta TEXT NOT NULL,
                codigo_carta TEXT NOT NULL,
                colecao_id TEXT NOT NULL DEFAULT '',
                imagem_url TEXT NOT NULL DEFAULT '',
                preco_custo REAL NOT NULL CHECK (preco_custo >= 0),
                remessa_id INTEGER NOT NULL,
                preco_remessa REAL NOT NULL DEFAULT 0 CHECK (preco_remessa >= 0),
                custo_final REAL NOT NULL DEFAULT 0 CHECK (custo_final >= 0),
                preco_venda_minimo REAL NOT NULL CHECK (preco_venda_minimo >= 0),
                status TEXT NOT NULL DEFAULT 'em estoque'
                    CHECK (status IN ('em estoque', 'vendido', 'separado', 'enviado', 'entregue')),
                cliente TEXT NOT NULL DEFAULT '',
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (remessa_id) REFERENCES remessas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS boosters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome_colecao TEXT NOT NULL,
                quantidade_booster INTEGER NOT NULL CHECK (quantidade_booster > 0),
                preco_custo REAL NOT NULL CHECK (preco_custo >= 0),
                remessa_id INTEGER NOT NULL,
                custo_final REAL NOT NULL DEFAULT 0 CHECK (custo_final >= 0),
                custo_minimo REAL NOT NULL CHECK (custo_minimo >= 0),
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (remessa_id) REFERENCES remessas(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS pedidos_booster (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                booster_id INTEGER NOT NULL,
                quantidade_boosters INTEGER NOT NULL CHECK (quantidade_boosters > 0),
                cliente TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'separado'
                    CHECK (status IN ('vendido', 'separado', 'enviado', 'entregue')),
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (booster_id) REFERENCES boosters(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS pedidos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tipo_item TEXT NOT NULL CHECK (tipo_item IN ('carta', 'booster')),
                carta_id INTEGER,
                booster_id INTEGER,
                quantidade INTEGER NOT NULL CHECK (quantidade > 0),
                cliente TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'separado'
                    CHECK (status IN ('vendido', 'separado', 'enviado', 'entregue')),
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (carta_id) REFERENCES cartas(id) ON DELETE CASCADE,
                FOREIGN KEY (booster_id) REFERENCES boosters(id) ON DELETE CASCADE,
                CHECK (
                    (tipo_item = 'carta' AND carta_id IS NOT NULL AND booster_id IS NULL AND quantidade = 1)
                    OR
                    (tipo_item = 'booster' AND booster_id IS NOT NULL AND carta_id IS NULL)
                )
            );
            """
        )
        cartas_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cartas'"
        ).fetchone()
        if cartas_sql and "em remessa" in (cartas_sql["sql"] or ""):
            conn.executescript(
                """
                ALTER TABLE cartas RENAME TO cartas_old_mig;
                CREATE TABLE cartas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome_carta TEXT NOT NULL,
                    codigo_carta TEXT NOT NULL,
                    colecao_id TEXT NOT NULL DEFAULT '',
                    imagem_url TEXT NOT NULL DEFAULT '',
                    preco_custo REAL NOT NULL CHECK (preco_custo >= 0),
                    remessa_id INTEGER NOT NULL,
                    preco_remessa REAL NOT NULL DEFAULT 0 CHECK (preco_remessa >= 0),
                    custo_final REAL NOT NULL DEFAULT 0 CHECK (custo_final >= 0),
                    preco_venda_minimo REAL NOT NULL CHECK (preco_venda_minimo >= 0),
                    status TEXT NOT NULL DEFAULT 'em estoque'
                        CHECK (status IN ('em estoque', 'vendido', 'separado', 'enviado', 'entregue')),
                    cliente TEXT NOT NULL DEFAULT '',
                    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (remessa_id) REFERENCES remessas(id) ON DELETE CASCADE
                );
                INSERT INTO cartas (id, nome_carta, codigo_carta, colecao_id, imagem_url, preco_custo, remessa_id, preco_remessa, custo_final, preco_venda_minimo, status, cliente, criado_em)
                SELECT
                    id, nome_carta, codigo_carta, '', '', preco_custo, remessa_id, preco_remessa, custo_final, preco_venda_minimo,
                    CASE WHEN status = 'em remessa' THEN 'em estoque' ELSE status END,
                    cliente, criado_em
                FROM cartas_old_mig;
                DROP TABLE cartas_old_mig;
                """
            )

        cartas_cols = conn.execute("PRAGMA table_info(cartas)").fetchall()
        if cartas_cols and not any(col["name"] == "colecao_id" for col in cartas_cols):
            conn.execute("ALTER TABLE cartas ADD COLUMN colecao_id TEXT NOT NULL DEFAULT ''")
        if cartas_cols and not any(col["name"] == "imagem_url" for col in cartas_cols):
            conn.execute("ALTER TABLE cartas ADD COLUMN imagem_url TEXT NOT NULL DEFAULT ''")
        cartas_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'cartas'"
        ).fetchone()
        if cartas_sql and "UNIQUE (colecao_id, codigo_carta)" in (cartas_sql["sql"] or ""):
            conn.executescript(
                """
                ALTER TABLE cartas RENAME TO cartas_uq_old_mig;
                CREATE TABLE cartas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome_carta TEXT NOT NULL,
                    codigo_carta TEXT NOT NULL,
                    colecao_id TEXT NOT NULL DEFAULT '',
                    imagem_url TEXT NOT NULL DEFAULT '',
                    preco_custo REAL NOT NULL CHECK (preco_custo >= 0),
                    remessa_id INTEGER NOT NULL,
                    preco_remessa REAL NOT NULL DEFAULT 0 CHECK (preco_remessa >= 0),
                    custo_final REAL NOT NULL DEFAULT 0 CHECK (custo_final >= 0),
                    preco_venda_minimo REAL NOT NULL CHECK (preco_venda_minimo >= 0),
                    status TEXT NOT NULL DEFAULT 'em estoque'
                        CHECK (status IN ('em estoque', 'vendido', 'separado', 'enviado', 'entregue')),
                    cliente TEXT NOT NULL DEFAULT '',
                    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (remessa_id) REFERENCES remessas(id) ON DELETE CASCADE
                );
                INSERT INTO cartas (
                    id, nome_carta, codigo_carta, colecao_id, imagem_url, preco_custo, remessa_id,
                    preco_remessa, custo_final, preco_venda_minimo, status, cliente, criado_em
                )
                SELECT
                    id, nome_carta, codigo_carta, COALESCE(colecao_id, ''), COALESCE(imagem_url, ''), preco_custo, remessa_id,
                    preco_remessa, custo_final, preco_venda_minimo, status, cliente, criado_em
                FROM cartas_uq_old_mig;
                DROP TABLE cartas_uq_old_mig;
                """
            )

        pedidos_cols = conn.execute("PRAGMA table_info(pedidos_booster)").fetchall()
        if pedidos_cols and not any(col["name"] == "status" for col in pedidos_cols):
            conn.execute(
                "ALTER TABLE pedidos_booster ADD COLUMN status TEXT NOT NULL DEFAULT 'separado'"
            )

        pedidos_count = conn.execute("SELECT COUNT(*) AS n FROM pedidos").fetchone()
        old_pedidos_count = conn.execute("SELECT COUNT(*) AS n FROM pedidos_booster").fetchone()
        if pedidos_count and old_pedidos_count and int(pedidos_count["n"]) == 0 and int(old_pedidos_count["n"]) > 0:
            conn.execute(
                """
                INSERT INTO pedidos (id, tipo_item, carta_id, booster_id, quantidade, cliente, status, criado_em)
                SELECT id, 'booster', NULL, booster_id, quantidade_boosters, cliente, status, criado_em
                FROM pedidos_booster
                """
            )
        conn.commit()


def recalculate_remessa(conn: sqlite3.Connection, remessa_id: int) -> None:
    remessa = conn.execute(
        "SELECT valor_impostos, valor_frete FROM remessas WHERE id = ?",
        (remessa_id,),
    ).fetchone()
    if not remessa:
        return

    custo_rateio = float(remessa["valor_impostos"]) + float(remessa["valor_frete"])

    cartas = conn.execute(
        "SELECT id, preco_custo FROM cartas WHERE remessa_id = ?",
        (remessa_id,),
    ).fetchall()
    boosters = conn.execute(
        "SELECT id, preco_custo, quantidade_booster FROM boosters WHERE remessa_id = ?",
        (remessa_id,),
    ).fetchall()

    itens: list[tuple[str, int, float]] = []
    total_base = 0.0

    for c in cartas:
        base = float(c["preco_custo"])
        itens.append(("carta", int(c["id"]), base))
        total_base += base

    for b in boosters:
        base = float(b["preco_custo"]) * int(b["quantidade_booster"])
        itens.append(("booster", int(b["id"]), base))
        total_base += base

    for tipo, item_id, base in itens:
        parcela = 0.0 if total_base <= 0 else custo_rateio * (base / total_base)
        if tipo == "carta":
            custo_final = base + parcela
            conn.execute(
                "UPDATE cartas SET preco_remessa = ?, custo_final = ? WHERE id = ?",
                (parcela, custo_final, item_id),
            )
        else:
            custo_final = base + parcela
            conn.execute(
                "UPDATE boosters SET custo_final = ? WHERE id = ?",
                (custo_final, item_id),
            )


def ensure_remessa(conn: sqlite3.Connection, remessa_id: int) -> None:
    exists = conn.execute("SELECT id FROM remessas WHERE id = ?", (remessa_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Remessa nao encontrada.")


def ensure_booster(conn: sqlite3.Connection, booster_id: int) -> None:
    exists = conn.execute("SELECT id FROM boosters WHERE id = ?", (booster_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Booster nao encontrado.")


def ensure_carta(conn: sqlite3.Connection, carta_id: int) -> None:
    exists = conn.execute("SELECT id FROM cartas WHERE id = ?", (carta_id,)).fetchone()
    if not exists:
        raise HTTPException(status_code=404, detail="Carta nao encontrada.")


def apply_booster_order_delta(conn: sqlite3.Connection, booster_id: int, ordered_delta: int) -> None:
    if ordered_delta == 0:
        return

    booster = conn.execute(
        "SELECT id, quantidade_booster FROM boosters WHERE id = ?",
        (booster_id,),
    ).fetchone()
    if not booster:
        raise HTTPException(status_code=404, detail="Booster nao encontrado.")

    disponivel_atual = int(booster["quantidade_booster"])
    novo_disponivel = disponivel_atual - ordered_delta
    if novo_disponivel < 0:
        raise HTTPException(
            status_code=409,
            detail="Quantidade insuficiente de boosters disponiveis para este pedido.",
        )
    conn.execute(
        "UPDATE boosters SET quantidade_booster = ? WHERE id = ?",
        (novo_disponivel, booster_id),
    )


def sync_carta_with_latest_order(conn: sqlite3.Connection, carta_id: int) -> None:
    latest = conn.execute(
        """
        SELECT status, cliente
        FROM pedidos
        WHERE tipo_item = 'carta' AND carta_id = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (carta_id,),
    ).fetchone()
    if latest:
        conn.execute(
            "UPDATE cartas SET status = ?, cliente = ? WHERE id = ?",
            (str(latest["status"]), str(latest["cliente"]), carta_id),
        )
        return
    conn.execute(
        "UPDATE cartas SET status = 'em estoque', cliente = '' WHERE id = ?",
        (carta_id,),
    )


def ensure_carta_without_order_conflict(
    conn: sqlite3.Connection, carta_id: int, ignore_pedido_id: int | None = None
) -> None:
    sql = "SELECT id FROM pedidos WHERE tipo_item = 'carta' AND carta_id = ?"
    params: tuple[int, ...] | tuple[int, int]
    params = (carta_id,)
    if ignore_pedido_id is not None:
        sql += " AND id != ?"
        params = (carta_id, ignore_pedido_id)
    exists = conn.execute(sql, params).fetchone()
    if exists:
        raise HTTPException(status_code=409, detail="Esta carta ja possui pedido cadastrado.")


def fetch_pedido_with_refs(conn: sqlite3.Connection, pedido_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """
        SELECT
            p.*,
            c.nome_carta,
            c.codigo_carta,
            b.nome_colecao
        FROM pedidos p
        LEFT JOIN cartas c ON c.id = p.carta_id
        LEFT JOIN boosters b ON b.id = p.booster_id
        WHERE p.id = ?
        """,
        (pedido_id,),
    ).fetchone()


class RemessaIn(BaseModel):
    nome: str = Field(min_length=1)
    valor_remessa: float = Field(ge=0)
    valor_impostos: float = Field(ge=0)
    valor_frete: float = Field(ge=0)


class CartaIn(BaseModel):
    nome_carta: str = Field(min_length=1)
    codigo_carta: str = Field(min_length=1)
    colecao_id: str = ""
    imagem_url: str = ""
    preco_custo: float = Field(ge=0)
    remessa_id: int = Field(gt=0)
    preco_venda_minimo: float = Field(ge=0)
    status: StatusCarta = "em estoque"
    cliente: str = ""


class BoosterIn(BaseModel):
    nome_colecao: str = Field(min_length=1)
    quantidade_booster: int = Field(gt=0)
    preco_custo: float = Field(ge=0)
    remessa_id: int = Field(gt=0)
    custo_minimo: float = Field(ge=0)


class PedidoIn(BaseModel):
    tipo_item: Literal["carta", "booster"]
    carta_id: int | None = Field(default=None, gt=0)
    booster_id: int | None = Field(default=None, gt=0)
    quantidade: int = Field(default=1, gt=0)
    cliente: str = Field(min_length=1)
    status: StatusPedido = "separado"


class PedidoBoosterCompatIn(BaseModel):
    booster_id: int = Field(gt=0)
    quantidade_boosters: int = Field(gt=0)
    cliente: str = Field(min_length=1)
    status: StatusPedido = "separado"


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/")
def health() -> dict:
    return {"ok": True, "servico": "controle-estoque-pokemon-api"}


@app.get("/integracoes/pokewallet/sets")
def listar_sets_pokewallet(language: str = Query(default="jap")) -> dict:
    language_norm = normalize_pokewallet_language(language)
    data = pokewallet_json_get("/sets", {})
    raw_sets = data.get("data")
    if not isinstance(raw_sets, list):
        raise HTTPException(status_code=502, detail="Resposta invalida da Pokewallet para sets.")

    dedup: dict[str, dict] = {}
    for item in raw_sets:
        if not isinstance(item, dict):
            continue
        set_code = str(item.get("set_code") or "").strip().upper()
        if not set_code:
            continue
        set_lang = normalize_pokewallet_language(str(item.get("language") or ""))
        if language_norm and set_lang != language_norm:
            continue
        if set_code in dedup:
            continue
        dedup[set_code] = {
            "id": set_code,
            "name": str(item.get("name") or "").strip() or set_code,
            "set_id": str(item.get("set_id") or "").strip(),
            "language": set_lang,
        }

    sets = sorted(dedup.values(), key=lambda item: (item["id"], item["name"]))
    return {"provider": "pokewallet", "language": language_norm, "sets": sets}


@app.get("/integracoes/pokewallet/resolver")
def resolver_imagem_pokewallet(
    colecao_id: str = Query(min_length=1),
    codigo_carta: str = Query(min_length=1),
    nome_carta: str = Query(default=""),
) -> dict:
    codigo_norm = normalize_card_number(codigo_carta)
    if not codigo_norm:
        raise HTTPException(status_code=400, detail="Codigo de carta invalido.")

    set_norm = normalize_card_code(colecao_id)
    queries: list[str] = []
    if set_norm:
        queries.append(f"{set_norm} {codigo_norm}")
    if nome_carta.strip():
        queries.append(f"{nome_carta.strip()} {set_norm} {codigo_norm}".strip())
    queries.append(codigo_norm)

    seen: set[str] = set()
    for q in queries:
        cleaned = " ".join(q.split())
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        data = pokewallet_json_get("/search", {"q": cleaned, "limit": "50"})
        results = data.get("results")
        if not isinstance(results, list) or not results:
            continue
        match = pick_pokewallet_card(results, colecao_id=colecao_id, codigo_carta=codigo_carta)
        if not match:
            continue
        card_id = str(match.get("id") or "").strip()
        if not card_id:
            continue
        card_info = match.get("card_info") or {}
        return {
            "found": True,
            "provider": "pokewallet",
            "card_id": card_id,
            "nome": card_info.get("name") or "",
            "set_code": card_info.get("set_code") or "",
            "card_number": card_info.get("card_number") or "",
        }

    return {"found": False, "provider": "pokewallet"}


@app.get("/integracoes/pokewallet/images/{card_id}")
def proxy_imagem_pokewallet(
    card_id: str,
    size: Literal["low", "high"] = "low",
) -> Response:
    api_key = get_pokewallet_key()
    encoded_id = url_parse.quote(card_id, safe="")
    url = f"{POKEWALLET_BASE_URL}/images/{encoded_id}?{url_parse.urlencode({'size': size})}"
    last_forbidden_detail = "Erro 403 ao buscar imagem na Pokewallet."
    for auth_headers in pokewallet_auth_headers_variants(api_key):
        req = url_request.Request(
            url,
            headers={**auth_headers, **pokewallet_client_headers()},
            method="GET",
        )
        try:
            with url_request.urlopen(req, timeout=12) as resp:
                media_type = resp.headers.get("Content-Type", "image/jpeg")
                data = resp.read()
                return Response(
                    content=data,
                    media_type=media_type,
                    headers={"Cache-Control": "public, max-age=86400"},
                )
        except url_error.HTTPError as exc:
            if exc.code == 403:
                last_forbidden_detail = parse_http_error_detail(exc, last_forbidden_detail)
                continue
            if exc.code == 404:
                raise HTTPException(status_code=404, detail="Imagem nao encontrada na Pokewallet.")
            detail = parse_http_error_detail(exc, f"Erro {exc.code} ao buscar imagem na Pokewallet.")
            raise HTTPException(status_code=exc.code, detail=detail)
        except url_error.URLError:
            raise HTTPException(status_code=502, detail="Falha ao conectar na Pokewallet.")
    raise HTTPException(status_code=403, detail=last_forbidden_detail)


@app.get("/dashboard")
def dashboard() -> dict:
    with closing(get_conn()) as conn:
        remessas = conn.execute("SELECT COUNT(*) AS n FROM remessas").fetchone()["n"]
        cartas = conn.execute("SELECT COUNT(*) AS n FROM cartas").fetchone()["n"]
        boosters = conn.execute("SELECT COUNT(*) AS n FROM boosters").fetchone()["n"]
        pedidos = conn.execute("SELECT COUNT(*) AS n FROM pedidos").fetchone()["n"]

        status_rows = conn.execute(
            "SELECT status, COUNT(*) AS quantidade FROM cartas GROUP BY status ORDER BY quantidade DESC"
        ).fetchall()

        financeiro = conn.execute(
            """
            SELECT
                (SELECT COALESCE(SUM(valor_remessa), 0) FROM remessas) AS valor_remessas,
                (SELECT COALESCE(SUM(valor_impostos + valor_frete), 0) FROM remessas) AS custos_rateados,
                (SELECT COALESCE(SUM(preco_custo), 0) FROM cartas) AS custo_base_cartas,
                (SELECT COALESCE(SUM(custo_final), 0) FROM cartas) AS custo_final_cartas,
                (SELECT COALESCE(SUM(preco_custo * quantidade_booster), 0) FROM boosters) AS custo_base_boosters,
                (SELECT COALESCE(SUM(custo_final), 0) FROM boosters) AS custo_final_boosters
            """
        ).fetchone()

        return {
            "totais": {
                "remessas": remessas,
                "cartas": cartas,
                "boosters": boosters,
                "pedidos_booster": pedidos,
            },
            "cartas_por_status": [dict(r) for r in status_rows],
            "financeiro": dict(financeiro),
        }


@app.post("/remessas", status_code=201)
def criar_remessa(payload: RemessaIn) -> dict:
    with closing(get_conn()) as conn:
        try:
            cursor = conn.execute(
                """
                INSERT INTO remessas (nome, valor_remessa, valor_impostos, valor_frete)
                VALUES (?, ?, ?, ?)
                """,
                (
                    payload.nome.strip(),
                    payload.valor_remessa,
                    payload.valor_impostos,
                    payload.valor_frete,
                ),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Nome de remessa ja existe.")

        row = conn.execute("SELECT * FROM remessas WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)


@app.get("/remessas")
def listar_remessas() -> list[dict]:
    with closing(get_conn()) as conn:
        rows = conn.execute("SELECT * FROM remessas ORDER BY id DESC").fetchall()
        return [dict(r) for r in rows]


@app.get("/remessas/{remessa_id}")
def obter_remessa(remessa_id: int) -> dict:
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT * FROM remessas WHERE id = ?", (remessa_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Remessa nao encontrada.")
        return dict(row)


@app.put("/remessas/{remessa_id}")
def atualizar_remessa(remessa_id: int, payload: RemessaIn) -> dict:
    with closing(get_conn()) as conn:
        exists = conn.execute("SELECT id FROM remessas WHERE id = ?", (remessa_id,)).fetchone()
        if not exists:
            raise HTTPException(status_code=404, detail="Remessa nao encontrada.")

        try:
            conn.execute(
                """
                UPDATE remessas
                SET nome = ?, valor_remessa = ?, valor_impostos = ?, valor_frete = ?
                WHERE id = ?
                """,
                (
                    payload.nome.strip(),
                    payload.valor_remessa,
                    payload.valor_impostos,
                    payload.valor_frete,
                    remessa_id,
                ),
            )
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Nome de remessa ja existe.")

        recalculate_remessa(conn, remessa_id)
        conn.commit()
        row = conn.execute("SELECT * FROM remessas WHERE id = ?", (remessa_id,)).fetchone()
        return dict(row)


@app.delete("/remessas/{remessa_id}", status_code=204)
def remover_remessa(remessa_id: int) -> None:
    with closing(get_conn()) as conn:
        deleted = conn.execute("DELETE FROM remessas WHERE id = ?", (remessa_id,)).rowcount
        conn.commit()
        if deleted == 0:
            raise HTTPException(status_code=404, detail="Remessa nao encontrada.")


@app.post("/cartas", status_code=201)
def criar_carta(payload: CartaIn) -> dict:
    with closing(get_conn()) as conn:
        ensure_remessa(conn, payload.remessa_id)
        try:
            cursor = conn.execute(
                """
                INSERT INTO cartas (
                    nome_carta, codigo_carta, colecao_id, imagem_url, preco_custo, remessa_id,
                    preco_venda_minimo, status, cliente
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.nome_carta.strip(),
                    payload.codigo_carta.strip(),
                    payload.colecao_id.strip(),
                    payload.imagem_url.strip(),
                    payload.preco_custo,
                    payload.remessa_id,
                    payload.preco_venda_minimo,
                    "em estoque",
                    "",
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail=f"Conflito ao salvar carta: {exc}")

        recalculate_remessa(conn, payload.remessa_id)
        conn.commit()
        row = conn.execute("SELECT * FROM cartas WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)


@app.get("/cartas")
def listar_cartas() -> list[dict]:
    with closing(get_conn()) as conn:
        rows = conn.execute(
            """
            SELECT c.*, r.nome AS remessa_nome
            FROM cartas c
            JOIN remessas r ON r.id = c.remessa_id
            ORDER BY c.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/cartas/{carta_id}")
def obter_carta(carta_id: int) -> dict:
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT * FROM cartas WHERE id = ?", (carta_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Carta nao encontrada.")
        return dict(row)


@app.put("/cartas/{carta_id}")
def atualizar_carta(carta_id: int, payload: CartaIn) -> dict:
    with closing(get_conn()) as conn:
        atual = conn.execute("SELECT remessa_id FROM cartas WHERE id = ?", (carta_id,)).fetchone()
        if not atual:
            raise HTTPException(status_code=404, detail="Carta nao encontrada.")
        ensure_remessa(conn, payload.remessa_id)

        try:
            conn.execute(
                """
                UPDATE cartas
                SET nome_carta = ?, codigo_carta = ?, colecao_id = ?, imagem_url = ?, preco_custo = ?, remessa_id = ?,
                    preco_venda_minimo = ?
                WHERE id = ?
                """,
                (
                    payload.nome_carta.strip(),
                    payload.codigo_carta.strip(),
                    payload.colecao_id.strip(),
                    payload.imagem_url.strip(),
                    payload.preco_custo,
                    payload.remessa_id,
                    payload.preco_venda_minimo,
                    carta_id,
                ),
            )
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail=f"Conflito ao salvar carta: {exc}")

        recalculate_remessa(conn, int(atual["remessa_id"]))
        if payload.remessa_id != int(atual["remessa_id"]):
            recalculate_remessa(conn, payload.remessa_id)
        conn.commit()
        row = conn.execute("SELECT * FROM cartas WHERE id = ?", (carta_id,)).fetchone()
        return dict(row)


@app.delete("/cartas/{carta_id}", status_code=204)
def remover_carta(carta_id: int) -> None:
    with closing(get_conn()) as conn:
        atual = conn.execute("SELECT remessa_id FROM cartas WHERE id = ?", (carta_id,)).fetchone()
        if not atual:
            raise HTTPException(status_code=404, detail="Carta nao encontrada.")
        conn.execute("DELETE FROM cartas WHERE id = ?", (carta_id,))
        recalculate_remessa(conn, int(atual["remessa_id"]))
        conn.commit()


@app.post("/boosters", status_code=201)
def criar_booster(payload: BoosterIn) -> dict:
    with closing(get_conn()) as conn:
        ensure_remessa(conn, payload.remessa_id)
        cursor = conn.execute(
            """
            INSERT INTO boosters (
                nome_colecao, quantidade_booster, preco_custo, remessa_id, custo_minimo
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                payload.nome_colecao.strip(),
                payload.quantidade_booster,
                payload.preco_custo,
                payload.remessa_id,
                payload.custo_minimo,
            ),
        )
        recalculate_remessa(conn, payload.remessa_id)
        conn.commit()
        row = conn.execute("SELECT * FROM boosters WHERE id = ?", (cursor.lastrowid,)).fetchone()
        return dict(row)


@app.get("/boosters")
def listar_boosters() -> list[dict]:
    with closing(get_conn()) as conn:
        rows = conn.execute(
            """
            SELECT b.*, r.nome AS remessa_nome
            FROM boosters b
            JOIN remessas r ON r.id = b.remessa_id
            ORDER BY b.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/boosters/{booster_id}")
def obter_booster(booster_id: int) -> dict:
    with closing(get_conn()) as conn:
        row = conn.execute("SELECT * FROM boosters WHERE id = ?", (booster_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Booster nao encontrado.")
        return dict(row)


@app.put("/boosters/{booster_id}")
def atualizar_booster(booster_id: int, payload: BoosterIn) -> dict:
    with closing(get_conn()) as conn:
        atual = conn.execute("SELECT remessa_id FROM boosters WHERE id = ?", (booster_id,)).fetchone()
        if not atual:
            raise HTTPException(status_code=404, detail="Booster nao encontrado.")
        ensure_remessa(conn, payload.remessa_id)

        conn.execute(
            """
            UPDATE boosters
            SET nome_colecao = ?, quantidade_booster = ?, preco_custo = ?, remessa_id = ?, custo_minimo = ?
            WHERE id = ?
            """,
            (
                payload.nome_colecao.strip(),
                payload.quantidade_booster,
                payload.preco_custo,
                payload.remessa_id,
                payload.custo_minimo,
                booster_id,
            ),
        )

        recalculate_remessa(conn, int(atual["remessa_id"]))
        if payload.remessa_id != int(atual["remessa_id"]):
            recalculate_remessa(conn, payload.remessa_id)
        conn.commit()
        row = conn.execute("SELECT * FROM boosters WHERE id = ?", (booster_id,)).fetchone()
        return dict(row)


@app.delete("/boosters/{booster_id}", status_code=204)
def remover_booster(booster_id: int) -> None:
    with closing(get_conn()) as conn:
        atual = conn.execute("SELECT remessa_id FROM boosters WHERE id = ?", (booster_id,)).fetchone()
        if not atual:
            raise HTTPException(status_code=404, detail="Booster nao encontrado.")
        conn.execute("DELETE FROM boosters WHERE id = ?", (booster_id,))
        recalculate_remessa(conn, int(atual["remessa_id"]))
        conn.commit()


@app.post("/pedidos", status_code=201)
def criar_pedido(payload: PedidoIn) -> dict:
    with closing(get_conn()) as conn:
        tipo_item = payload.tipo_item
        carta_id = payload.carta_id
        booster_id = payload.booster_id
        quantidade = payload.quantidade
        cliente = payload.cliente.strip()
        if not cliente:
            raise HTTPException(status_code=400, detail="Cliente obrigatorio.")

        if tipo_item == "carta":
            if carta_id is None or booster_id is not None or quantidade != 1:
                raise HTTPException(
                    status_code=400,
                    detail="Pedido de carta deve informar apenas carta_id e quantidade = 1.",
                )
            ensure_carta(conn, carta_id)
            ensure_carta_without_order_conflict(conn, carta_id)
        else:
            if booster_id is None or carta_id is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Pedido de booster deve informar apenas booster_id.",
                )
            apply_booster_order_delta(conn, booster_id, quantidade)

        cursor = conn.execute(
            """
            INSERT INTO pedidos (tipo_item, carta_id, booster_id, quantidade, cliente, status)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (tipo_item, carta_id, booster_id, quantidade, cliente, payload.status),
        )
        pedido_id = int(cursor.lastrowid)
        if tipo_item == "carta" and carta_id is not None:
            sync_carta_with_latest_order(conn, carta_id)
        conn.commit()
        row = fetch_pedido_with_refs(conn, pedido_id)
        return dict(row) if row else {}


@app.get("/pedidos")
def listar_pedidos() -> list[dict]:
    with closing(get_conn()) as conn:
        rows = conn.execute(
            """
            SELECT
                p.*,
                c.nome_carta,
                c.codigo_carta,
                b.nome_colecao
            FROM pedidos p
            LEFT JOIN cartas c ON c.id = p.carta_id
            LEFT JOIN boosters b ON b.id = p.booster_id
            ORDER BY p.id DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/pedidos/{pedido_id}")
def obter_pedido(pedido_id: int) -> dict:
    with closing(get_conn()) as conn:
        row = fetch_pedido_with_refs(conn, pedido_id)
        if not row:
            raise HTTPException(status_code=404, detail="Pedido nao encontrado.")
        return dict(row)


@app.get("/boosters/{booster_id}/pedidos")
def listar_pedidos_por_booster(booster_id: int) -> list[dict]:
    with closing(get_conn()) as conn:
        ensure_booster(conn, booster_id)
        rows = conn.execute(
            """
            SELECT p.*, b.nome_colecao
            FROM pedidos p
            JOIN boosters b ON b.id = p.booster_id
            WHERE p.tipo_item = 'booster' AND p.booster_id = ?
            ORDER BY p.id DESC
            """,
            (booster_id,),
        ).fetchall()
        return [dict(r) for r in rows]


@app.put("/pedidos/{pedido_id}")
def atualizar_pedido(pedido_id: int, payload: PedidoIn) -> dict:
    with closing(get_conn()) as conn:
        atual = conn.execute(
            "SELECT id, tipo_item, carta_id, booster_id, quantidade FROM pedidos WHERE id = ?",
            (pedido_id,),
        ).fetchone()
        if not atual:
            raise HTTPException(status_code=404, detail="Pedido nao encontrado.")

        old_tipo = str(atual["tipo_item"])
        old_carta_id = int(atual["carta_id"]) if atual["carta_id"] is not None else None
        old_booster_id = int(atual["booster_id"]) if atual["booster_id"] is not None else None
        old_quantidade = int(atual["quantidade"])

        if old_tipo == "booster" and old_booster_id is not None:
            apply_booster_order_delta(conn, old_booster_id, -old_quantidade)

        tipo_item = payload.tipo_item
        carta_id = payload.carta_id
        booster_id = payload.booster_id
        quantidade = payload.quantidade
        cliente = payload.cliente.strip()
        if not cliente:
            raise HTTPException(status_code=400, detail="Cliente obrigatorio.")

        if tipo_item == "carta":
            if carta_id is None or booster_id is not None or quantidade != 1:
                raise HTTPException(
                    status_code=400,
                    detail="Pedido de carta deve informar apenas carta_id e quantidade = 1.",
                )
            ensure_carta(conn, carta_id)
            ensure_carta_without_order_conflict(conn, carta_id, ignore_pedido_id=pedido_id)
        else:
            if booster_id is None or carta_id is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Pedido de booster deve informar apenas booster_id.",
                )
            apply_booster_order_delta(conn, booster_id, quantidade)

        conn.execute(
            """
            UPDATE pedidos
            SET tipo_item = ?, carta_id = ?, booster_id = ?, quantidade = ?, cliente = ?, status = ?
            WHERE id = ?
            """,
            (tipo_item, carta_id, booster_id, quantidade, cliente, payload.status, pedido_id),
        )

        if old_tipo == "carta" and old_carta_id is not None:
            sync_carta_with_latest_order(conn, old_carta_id)
        if tipo_item == "carta" and carta_id is not None:
            sync_carta_with_latest_order(conn, carta_id)

        conn.commit()
        row = fetch_pedido_with_refs(conn, pedido_id)
        return dict(row) if row else {}


@app.delete("/pedidos/{pedido_id}", status_code=204)
def remover_pedido(pedido_id: int) -> None:
    with closing(get_conn()) as conn:
        pedido = conn.execute(
            "SELECT tipo_item, carta_id, booster_id, quantidade FROM pedidos WHERE id = ?",
            (pedido_id,),
        ).fetchone()
        if not pedido:
            raise HTTPException(status_code=404, detail="Pedido nao encontrado.")

        tipo_item = str(pedido["tipo_item"])
        carta_id = int(pedido["carta_id"]) if pedido["carta_id"] is not None else None
        booster_id = int(pedido["booster_id"]) if pedido["booster_id"] is not None else None
        quantidade = int(pedido["quantidade"])

        if tipo_item == "booster" and booster_id is not None:
            apply_booster_order_delta(conn, booster_id, -quantidade)

        conn.execute("DELETE FROM pedidos WHERE id = ?", (pedido_id,))

        if tipo_item == "carta" and carta_id is not None:
            sync_carta_with_latest_order(conn, carta_id)

        conn.commit()


@app.post("/pedidos-booster", status_code=201)
def criar_pedido_booster_compat(payload: PedidoBoosterCompatIn) -> dict:
    return criar_pedido(
        PedidoIn(
            tipo_item="booster",
            booster_id=payload.booster_id,
            quantidade=payload.quantidade_boosters,
            cliente=payload.cliente,
            status=payload.status,
        )
    )


@app.get("/pedidos-booster")
def listar_pedidos_booster_compat() -> list[dict]:
    pedidos = listar_pedidos()
    return [p for p in pedidos if p.get("tipo_item") == "booster"]


@app.get("/pedidos-booster/{pedido_id}")
def obter_pedido_booster_compat(pedido_id: int) -> dict:
    pedido = obter_pedido(pedido_id)
    if pedido.get("tipo_item") != "booster":
        raise HTTPException(status_code=404, detail="Pedido de booster nao encontrado.")
    return pedido


@app.put("/pedidos-booster/{pedido_id}")
def atualizar_pedido_booster_compat(pedido_id: int, payload: PedidoBoosterCompatIn) -> dict:
    return atualizar_pedido(
        pedido_id,
        PedidoIn(
            tipo_item="booster",
            booster_id=payload.booster_id,
            quantidade=payload.quantidade_boosters,
            cliente=payload.cliente,
            status=payload.status,
        ),
    )


@app.delete("/pedidos-booster/{pedido_id}", status_code=204)
def remover_pedido_booster_compat(pedido_id: int) -> None:
    pedido = obter_pedido(pedido_id)
    if pedido.get("tipo_item") != "booster":
        raise HTTPException(status_code=404, detail="Pedido de booster nao encontrado.")
    remover_pedido(pedido_id)
