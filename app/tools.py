from typing import List, Optional, Dict, Any
import httpx
import os
import asyncio
import numpy as np
from openai import AsyncOpenAI
from .models import SuggestionRequest, SuggestionResult, MenuItem, CategoriaProduto
from .logger import VisualLogger

API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:3000/api/v1")

# Credenciais (devem ser configuradas no .env)
AUTH_EMAIL = os.getenv("AUTH_EMAIL")
AUTH_PASSWORD = os.getenv("AUTH_PASSWORD")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Cache de Embeddings (Em Memória)
# Dict[str_id, Dict[str, Any]] -> armazena item completo + 'embedding'
CACHE_MENU_EMBEDDINGS: Dict[str, Dict[str, Any]] = {}

openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

async def get_access_token() -> Optional[str]:
    """Realiza login e retorna o access_token."""
    async with httpx.AsyncClient() as client:
        try:
            payload = {"email": AUTH_EMAIL, "password": AUTH_PASSWORD}
            response = await client.post(f"{API_BASE_URL}/auth/login", json=payload, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            return data.get("access_token")
        except Exception as e:
            print(f"Erro no Login: {e}")
            return None

async def fetch_menu_items() -> List[Dict[str, Any]]:
    """Busca todos os itens do menu da API, realizando login antes."""
    token = await get_access_token()
    if not token:
        return []

    headers = {"Authorization": f"Bearer {token}"}
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}/menu-items", headers=headers, timeout=10.0)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Erro na API de Menu: {e}")
            return []

async def fetch_category_names() -> str:
    """Busca árvore de categorias."""
    token = await get_access_token()
    if not token: return "Erro ao carregar categorias."
    
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(f"{API_BASE_URL}/categories", headers=headers, timeout=10.0)
            response.raise_for_status()
            data = response.json()
            lines = []
            for cat in data:
                if cat.get("pai"): continue
                name = cat.get("name", "")
                subs = [sub.get("name") for sub in cat.get("subcategories", [])]
                if subs: lines.append(f"- {name} ({', '.join(subs)})")
                else: lines.append(f"- {name}")
            return "\n".join(lines)
        except Exception:
            return "Indisponível no momento."

async def get_embedding(text: str) -> List[float]:
    """Gera embedding usando OpenAI ada-002 ou text-embedding-3-small."""
    try:
        text = text.replace("\n", " ")
        resp = await openai_client.embeddings.create(input=[text], model="text-embedding-3-small")
        return resp.data[0].embedding
    except Exception as e:
        print(f"Erro OpenAI Embedding: {e}")
        return []

async def refresh_menu_embeddings():
    """Atualiza o cache de embeddings do menu usando Batch Processing (Lote)."""
    global CACHE_MENU_EMBEDDINGS
    print(f"{VisualLogger.WARNING}🔄 Gerando Embeddings do Cardápio (Batch)...{VisualLogger.ENDC}")
    
    items = await fetch_menu_items()
    if not items: return

    # Prepara lista de textos e mapeamento de IDs
    valid_items = []
    texts_to_embed = []
    
    for item in items:
        item_id = item.get("id")
        if not item_id: continue
        
        name = item.get("name", "")
        desc = item.get("description", "") or ""
        cat = item.get("category", {}).get("name", "")
        tags = " ".join(item.get("tags") or [])
        
        # Texto para vetorização
        rich_text = f"{name} {desc} Categoria: {cat} Tags: {tags}".replace("\n", " ")
        
        texts_to_embed.append(rich_text)
        valid_items.append(item)
    
    if not texts_to_embed: return

    try:
        # Chamada ÚNICA para a API (Batch)
        # O modelo text-embedding-3-small aceita arrays de strings
        resp = await openai_client.embeddings.create(input=texts_to_embed, model="text-embedding-3-small")
        
        # Mapeia resultados de volta para os itens
        for i, embedding_data in enumerate(resp.data):
            # A ordem de resp.data é garantida ser a mesma de input
            item = valid_items[i]
            item["embedding"] = embedding_data.embedding
            CACHE_MENU_EMBEDDINGS[item["id"]] = item
            
        print(f"{VisualLogger.OKGREEN}✅ {len(CACHE_MENU_EMBEDDINGS)} Embeddings Gerados em 1 Batch!{VisualLogger.ENDC}")
        
    except Exception as e:
        print(f"{VisualLogger.FAIL}Erro Batch Embedding: {e}{VisualLogger.ENDC}")

async def pick_random_items(qtd: int = 3, category_focus: str = "todas") -> list[MenuItem]:
    """Seleciona itens aleatórios do cache para o modo 'Surpreenda-me'."""
    import random
    
    if not CACHE_MENU_EMBEDDINGS:
        await refresh_menu_embeddings()
        
    candidate_items = []

    # 1. Se "todas", pegamos tudo.
    if category_focus.lower() == "todas":
        candidate_items = list(CACHE_MENU_EMBEDDINGS.values())
        random.shuffle(candidate_items)
        selected_raw = candidate_items[:qtd]

    else:
        # 2. Se tem foco (ex: "vinhos", "bebidas"), usamos Busca Vetorial!
        # Isso garante que "suco" seja encontrado perto de "bebidas" sem hardcode.
        nome_foco = category_focus.replace("_", " ") # ex: pratos_principais -> pratos principais
        vec_foco = await get_embedding(nome_foco)
        
        if not vec_foco:
            # Fallback seguro: pega tudo se falhar embedding
            candidate_items = list(CACHE_MENU_EMBEDDINGS.values())
            random.shuffle(candidate_items)
            selected_raw = candidate_items[:qtd]
        else:
            scored = []
            for item in CACHE_MENU_EMBEDDINGS.values():
                sim = cosine_similarity(vec_foco, item["embedding"])
                scored.append((sim, item))
            
            # Ordena por similaridade
            scored.sort(key=lambda x: x[0], reverse=True)
            
            # Pega o Top 10 (para ter variedade e não só o Top 1 sempre)
            top_candidates = [x[1] for x in scored[:10]]
            
            # Desses Top 10, escolhe aleatoriamente
            random.shuffle(top_candidates)
            selected_raw = top_candidates[:qtd]

    return [
        MenuItem(
            id=i["id"], 
            nome=i["name"], 
            preco=str(i["price"]), 
            categoria=i.get("category", {}).get("name", "Outros"), 
            descricao=i.get("description", "") or "Sem descrição disponível."
        ) for i in selected_raw
    ]

def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    return np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2))

async def agente_gastronomico(req: SuggestionRequest) -> SuggestionResult:
    VisualLogger.log_tool_call("agente_gastronomico", req.model_dump())
    
    # 1. Start Cache se Vazio
    if not CACHE_MENU_EMBEDDINGS:
        await refresh_menu_embeddings()
    
    if not CACHE_MENU_EMBEDDINGS:
        return SuggestionResult(sugestoes=[])

    # 2. Vetoriza Query do Usuário
    query_vec = await get_embedding(req.pedido_usuario)
    if not query_vec:
        return SuggestionResult(sugestoes=[])
        
    scored_items = []
    
    # 3. Busca Vetorial
    for item_id, item in CACHE_MENU_EMBEDDINGS.items():
        # 0. Filtro de Exclusão (Evitar repetições)
        if req.excluded_ids and item_id in req.excluded_ids:
            continue

        # Filtro Rigído de Categoria (opcional, ajuda a afunilar)
        cat_name = item.get("category", {}).get("name", "").lower()
        
        # Soft Filter de Categoria (opcional)
        # Se o usuário pediu "bebidas", podemos dar um "boost" em itens que contenham "bebida" ou similares no nome da categoria.
        # Mas para ser 100% sem hardcode, confiamos PRIMARIAMENTE no embedding da Query.
        # O embedding de "Quero beber algo refrescante" já vai trazer bebidas para o topo.
        
        # Opcional: Se 'categoria_foco' for definido e diferente de TODAS, podemos filtrar grosseiramente
        # apenas se houver match de string óbvio, senão deixamos passar.
        if req.categoria_foco != CategoriaProduto.TODAS:
            foco_str = req.categoria_foco.value.lower().replace("_", " ")
            cat_str = cat_name.lower()
            
            # Se a string da categoria NEM LEMBRA o foco, talvez pular?
            # Mas "suco" não contem "bebidas". Então Hard Filter por string é perigoso sem hardcode.
            # SOLUÇÃO: Não filtrar! A similaridade vetorial cuidará disso.
            pass
            
        similarity = cosine_similarity(query_vec, item["embedding"])
        
        if similarity > 0.15: 
            scored_items.append((similarity, item))
            
    # 4. Rankeamento com Serendipidade (Acaso)
    # Ordena por score
    scored_items.sort(key=lambda x: x[0], reverse=True)
    
    # Aumenta o pool inicial para o LLM poder escolher melhor
    candidates_for_llm = [item for _, item in scored_items[:25]] 
    
    if not candidates_for_llm:
        # Tenta fallback com itens aleatórios se a busca vetorial falhar muito
        # Mas apenas se não tiver NADA.
        pass

    # 5. Reranking Inteligente via LLM
    # Isso resolve o problema de "algo leve" retornar Coca-Cola só porque tem "light" ou similaridade baixa.
    # O LLM vai analisar os candidatos e filtrar o que realmente faz sentido.
    
    final_items = await _rank_items_with_llm(req.pedido_usuario, candidates_for_llm)
    
    # Se o LLM não retornar nada (erro ou filtro total), usar o Top 3 vetorial como fallback
    if not final_items and candidates_for_llm:
         final_items = candidates_for_llm[:3]

    results = []
    for item in final_items:
        results.append(MenuItem(
            id=item["id"],
            nome=item["name"],
            preco=str(item["price"]),
            categoria=item.get("category", {}).get("name", "Outros"),
            descricao=item.get("description", "") or "Sem descrição disponível."
        ))

    if not results:
        res = SuggestionResult(sugestoes=[])
        VisualLogger.log_tool_result(res, success=False)
        return res

    res = SuggestionResult(sugestoes=results)
    VisualLogger.log_tool_result(res, success=True)
    return res

async def _rank_items_with_llm(query: str, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Usa um LLM rápido (gpt-4o-mini) para filtrar e ordenar os itens candidatos
    baseado no pedido do usuário. A busca vetorial é 'burra' para nuances,
    o LLM é 'inteligente'.
    """
    if not items: return []
    
    # Prepara o prompt
    items_str = ""
    item_map = {}
    for item in items:
        # Sanitiza para economizar tokens e evitar confusão
        i_str = f"ID: {item['id']} | Nome: {item['name']} | Desc: {item.get('description','')} | Cat: {item.get('category',{}).get('name','')}"
        items_str += f"- {i_str}\n"
        item_map[item['id']] = item

    system_prompt = """
    Você é um especialista gastrômico inteligente. 
    Sua tarefa é selecionar os MELHORES itens de uma lista de candidatos para atender ao pedido do usuário.
    
    Regras:
    1. Retorne APENAS um JSON array de strings com os IDs dos itens escolhidos. Ex: ["id1", "id2"]
    2. Selecione de 0 a 3 itens. Se NENHUM item for adequado, retorne [].
    3. SEJA EXTREMAMENTE RIGOROSO. 
       - "Algo leve" -> APENAS saladas, peixes, grelhados leves ou entradas leves. NUNCA massas pesadas, frituras, carnes gordurosas ou frutos do mar.
       - "Doce" -> APENAS sobremesas, bolos, chocolates. NUNCA pratos salgados.
       - "Carne" -> APENAS carnes vermelhas. Frango e Peixe SÓ se o usuário pedir "carnes brancas" ou se não tiver outra opção.
    4. Se o pedido for "fome" ou genérico, você pode ser mais flexível.
    5. NÃO invente motivos. Se não serve, não mande. Melhor retornar lista vazia do que uma recomendação ruim.
    """
    
    user_prompt = f"""
    Pedido do Usuário: "{query}"
    
    Candidatos (Vetor Search):
    {items_str}
    
    Quais desses itens realmente atendem ao pedido? Responda com JSON array de IDs.
    """
    
    try:
        resp = await openai_client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            response_format={"type": "json_object"} 
        )
        
        content = resp.choices[0].message.content
        import json
        data = json.loads(content)
        
        # Tenta extrair a lista de IDs de várias formas comuns que o LLM pode mandar
        ids = []
        if isinstance(data, list):
            ids = data
        elif isinstance(data, dict):
            # Procura chaves comuns
            for k in ["ids", "items", "recomendados", "ids_recomendados", "result"]:
                if k in data and isinstance(data[k], list):
                    ids = data[k]
                    break
            
            # Se ainda não achou, pega o primeiro valor que for lista
            if not ids:
                for v in data.values():
                    if isinstance(v, list):
                        ids = v
                        break 
            
        ranked_items = []
        for i_id in ids:
            if i_id in item_map:
                ranked_items.append(item_map[i_id])
                
        # Fallback de segurança: se o LLM retornou IDs validos, usa.
        # Se retornou vazio, é pq REALMENTE não achou nada bom (filtro rigoroso).
        return ranked_items
        
    except Exception as e:
        print(f"Erro no Reranking LLM: {e}")
        return [] # Em caso de erro, retorna vazio para o caller usar fallback

