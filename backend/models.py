"""Models and type definitions."""
from typing import Literal
from pydantic import BaseModel, Field

StatusCarta = Literal["em estoque", "vendido", "separado", "enviado", "entregue"]
StatusPedido = Literal["vendido", "separado", "enviado", "entregue"]
TipoPedido = Literal["carta", "booster"]


class RemessaIn(BaseModel):
    nome: str
    valor: float
    valor_impostos: float
    valor_frete: float


class Remessa(RemessaIn):
    id: int
    criado_em: str


class CartaIn(BaseModel):
    nome_carta: str
    codigo_carta: str
    colecao_id: str
    preco_custo: float
    remessa_id: int
    preco_venda_minimo: float
    imagem_url: str = ""


class Carta(CartaIn):
    id: int
    remessa_id: int
    preco_remessa: float
    custo_final: float
    status: StatusCarta
    cliente: str
    criado_em: str
    remessa_nome: str | None = None
    codigo_carta: str = Field(default="")


class BoosterIn(BaseModel):
    nome_colecao: str
    quantidade_booster: int
    preco_custo: float
    remessa_id: int
    custo_minimo: float


class Booster(BoosterIn):
    id: int
    preco_remessa: float
    custo_final: float
    criado_em: str
    remessa_nome: str | None = None


class PedidoIn(BaseModel):
    tipo_item: TipoPedido
    carta_id: int | None = None
    booster_id: int | None = None
    quantidade: int = 1
    cliente: str
    status: StatusPedido


class Pedido(PedidoIn):
    id: int
    criado_em: str
    nome_carta: str | None = None
    codigo_carta: str | None = None
    nome_colecao: str | None = None
