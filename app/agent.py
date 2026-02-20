from pydantic_ai import Agent, RunContext
from dotenv import load_dotenv
from .models import MenuxResponse, SuggestionRequest, SuggestionResult, MenuxDeps

load_dotenv()

from .tools import agente_gastronomico
from .logger import VisualLogger
from .tools import pick_random_items, SuggestionResult

menux_agent = Agent(
    'openai:gpt-4o-mini',
    output_type=MenuxResponse,
    deps_type=MenuxDeps,
)

@menux_agent.system_prompt
def get_system_prompt(ctx: RunContext[MenuxDeps]) -> str:
    """Retorna o system prompt formatado com dados dinâmicos das dependências."""
    # Importação local para evitar ciclo circular se necessário, mas aqui ok
    from .prompts import SYSTEM_PROMPT
    from datetime import datetime
    
    categories_list = ctx.deps.categorias_str if ctx.deps else "Não carregado."
    
    # Formata o prompt final
    final_prompt = SYSTEM_PROMPT.format(
        current_date=datetime.now().strftime("%d-%m-%Y %H:%M"),
        categories=categories_list
    )
    
    # DEBUG: Mostra exatamente o que está indo para o LLM
    print(f"\n\033[93m🔮 [SYSTEM PROMPT DEBUG]\n{final_prompt}\n\033[0m")
    
    return final_prompt

@menux_agent.tool
async def consultar_cardapio(ctx: RunContext[MenuxDeps], req: SuggestionRequest) -> SuggestionResult:
    """
    Consulta o cardápio para buscar sugestões de pratos e bebidas.
    
    CRITÉRIOS DE USO:
    1. USE APENAS para intenção CLARA de compra ("Quero X", "Tem Y?").
    2. PROIBIDO USAR para saudações ("Oi", "Olá", "Tudo bem") ou perguntas vagas ("O que tem?", "Quais categorias?"). 
       Para isso, responda apenas como anfitrião e cite as categorias do prompt.
    3. Se o usuário falar "surpreenda-me", use `pedido_usuario="surpreenda-me"`.
    4. Se o usuário pedir "outra opção" ou rejeitar sugestões anteriores, passe os IDs dos itens rejeitados em `excluded_ids`.
    
    AVISO CRÍTICO:
    - Esta função deve ser chamada APENAS UMA VEZ por turno.
    - O conteúdo retornado é SUFICIENTE. Não tente "refinar" ou "buscar detalhes" chamando de novo.
    - Se vieram itens misturados, FILTRE na sua resposta textual, não chame a tool novamente.
    """
    # vai buscar direto da API. Aqui é só ponte.
    return await agente_gastronomico(req)

@menux_agent.tool
async def surpreenda_me(ctx: RunContext[MenuxDeps], req: SuggestionRequest) -> SuggestionResult:
    """
    Use esta ferramenta APENAS quando o usuário der LIBERDADE TOTAL ou pedir para SER SURPREENDIDO.
    Exemplos: "Escolha você", "Qualquer coisa serve", "Me surpreenda", "Tanto faz".
    
    Esta tool escolhe itens ALEATÓRIOS do cardápio.
     NÃO use se o usuário tiver intenção clara de busca (ex: "Quero algo com carne").
    """
    
    VisualLogger.log_tool_call("surpreenda_me", req.model_dump())
    
    items = await pick_random_items(qtd=3, category_focus=req.categoria_foco.value)
    
    if not items:
        return SuggestionResult(sugestoes=[])
        
    res = SuggestionResult(sugestoes=items)
    VisualLogger.log_tool_result(res, success=True)
    return res
