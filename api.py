import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from dotenv import load_dotenv

from contextlib import asynccontextmanager

import uuid
from datetime import datetime

from app.memory import RedisMemory
from app.tools import CACHE_MENU_EMBEDDINGS
from app.upsell import UpsellManager
from pydantic_ai.messages import ModelResponse, TextPart
from app.agent import menux_agent
from app.models import MenuxDeps, MenuxResponse
from app.tools import fetch_category_names, refresh_menu_embeddings

# 2. Estado Global (Cache de Contexto)
class APIState:
    def __init__(self):
        self.deps = MenuxDeps()

state = APIState()
memory_client = RedisMemory() # Conecta ao Redis

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Novo padrão do FastAPI para gerenciar o ciclo de vida (startup/shutdown).
    Substitui o antigo @app.on_event("startup").
    """
    print("🤖 Iniciando Menux AI Server...")
    try:
        # Carrega o cardápio e gera os embeddings no início
        cats_context = await fetch_category_names()
        state.deps.categorias_str = cats_context
        await refresh_menu_embeddings()
        print("✅ Servidor pronto e Cardápio carregado!")
    except Exception as e:
        print(f"❌ Erro crítico no startup: {e}")
    
    yield  # Aqui a API fica rodando
    
    print("👋 Encerrando Menux AI Server.")

app = FastAPI(title="Menux AI API", lifespan=lifespan)

# 3. CORS - Necessário para o Frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Modelos de Entrada/Saída
class ChatRequest(BaseModel):
    mensagem: str
    session_id: Optional[str] = None # Opcional por enquanto, se não vier geramos um uuid


# 5. Rota Principal de Chat
@app.post("/chat", response_model=MenuxResponse)
async def chat(request: ChatRequest):
    if not request.mensagem:
        raise HTTPException(status_code=400, detail="Mensagem vazia")
    
    session_id = request.session_id # Ou criar um se não vier (mas idealmente o front deve mandar)
    if not session_id:
        session_id = str(uuid.uuid4())

    try:
        # 1. Carrega histórico do Redis
        history = await memory_client.get_history(session_id)
        
        # 2. Executa o Agente com histórico persistido
        result = await menux_agent.run(
            request.mensagem, 
            deps=state.deps,
            message_history=history
        )
        
        
        upsell_data = await UpsellManager.check_upsell(
            result.output.ids_recomendados, 
            CACHE_MENU_EMBEDDINGS
        )
        
        new_msgs = result.new_messages()
        
        if upsell_data:
            # Injeta o upsell na resposta final
            result.output.upsell = upsell_data
            
            # Cria mensagem falsa do assistente para o histórico
            # Assim, se o usuário disser "Sim", o agente sabe do que ele está falando.
            fake_upsell_msg = ModelResponse(
                parts=[TextPart(content=upsell_data.message)],
                timestamp=datetime.now()
            )
            new_msgs.append(fake_upsell_msg)

        # 4. Salva novo histórico (append das novas mensagens + upsell se houver)
        await memory_client.save_history(session_id, new_msgs)
        
        return result.output
        
    except Exception as e:
        print(f"Erro no processamento do chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# 6. Rota de Saúde (Healthcheck)
@app.get("/health")
async def health():
    return {"status": "online", "menu_loaded": bool(state.deps.categorias_str)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
