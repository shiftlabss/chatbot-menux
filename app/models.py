from pydantic import BaseModel, Field
from typing import List, Optional
from enum import Enum
from dataclasses import dataclass

@dataclass
class MenuxDeps:
    categorias_str: str = ""
    restaurantId: str = ""

class CategoriaProduto(str, Enum):
    ENTRADAS = "entradas"
    MASSAS = "massas"
    PRATOS_PRINCIPAIS = "pratos_principais"
    SOBREMESAS = "sobremesas"
    BEBIDAS = "bebidas"
    VINHOS = "vinhos"
    TODAS = "todas"

# --- Upsell Schemas ---
class UpsellType(str, Enum):
    CROSS_SELL = "cross-sell"
    UPSELL = "upsell"

class UpsellData(BaseModel):
    items: List[str] = Field(..., description="IDs dos itens sugeridos para upsell/cross-sell")
    message: str = Field(..., description="Mensagem de gatilho para o usuário")
    type: UpsellType = Field(..., description="Tipo de oferta: cross-sell (acompanhamento) ou upsell (upgrade)")

# --- Contrato de Saída (Output Schema) ---
class MenuxResponse(BaseModel):
    resposta_chat: str = Field(
        ..., 
        description="Resposta amigável e encantadora ao usuário. Sem limite rígido de caracteres, explique o porquê da recomendação."
    )
    ids_recomendados: List[str] = Field(
        default_factory=list,
        description="Lista de IDs (UUIDs) dos produtos recomendados. Vazio se não houver recomendação."
    )
    upsell: Optional[UpsellData] = Field(
        None,
        description="Dados de Upsell/Cross-sell se disponível para o primeiro item recomendado."
    )

# --- Tool Schemas ---
class SuggestionRequest(BaseModel):
    pedido_usuario: str = Field(..., description="O pedido ou desejo do usuário extraído da conversa.")
    categoria_foco: CategoriaProduto = Field(
        default=CategoriaProduto.TODAS, 
        description="Categoria específica para filtrar a busca, se o usuário mencionar."
    )
    preferencias: Optional[str] = Field(None, description="Preferências culinárias explícitas.")
    restricoes: Optional[str] = Field(None, description="Restrições alimentares (ex: glúten, lactose).")
    excluded_ids: List[str] = Field(
        default_factory=list,
        description="Lista de IDs (UUIDs) de itens que JÁ foram sugeridos e devem ser evitados nesta nova busca."
    )

class MenuItem(BaseModel):
    id: str  # Mudança: API usa UUID string
    nome: str
    preco: str # Mudança: API retorna string "12.00"
    categoria: str # Mudança: API retorna objeto, vamos planificar para o nome da categoria
    descricao: str

class SuggestionResult(BaseModel):
    sugestoes: List[MenuItem]
