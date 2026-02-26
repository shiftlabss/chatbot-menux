import asyncio
import os
from dotenv import load_dotenv
from app.agent import menux_agent
from app.logger import VisualLogger
from app.tools import fetch_category_names, refresh_menu_embeddings
from app.models import MenuxDeps

# Carrega variáveis de ambiente
load_dotenv()

async def main():
    print("--- Menux (Python/PydanticAI) ---")
    
    # Recebe o ID do restaurante para teste local
    restaurant_id = input("Digite o ID do restaurante (ou Enter para 'test-rest-1'): ") or "test-rest-1"
    
    # Pre-loading de contexto
    print(f"🤖 Carregando categorias do cardápio para {restaurant_id}...")
    cats_context = await fetch_category_names(restaurant_id)
    deps = MenuxDeps(categorias_str=cats_context, restaurantId=restaurant_id)
    print("✅ Categorias Carregadas!")
    
    # Warmup do Cache de Embeddings
    print("🚀 Aquecendo motores (Gerando Embeddings)...")
    await refresh_menu_embeddings(restaurant_id)
    
    print("\nDigite 'sair' para encerrar.\n")
    
    # Histórico de mensagens para manter contexto (simulado)
    # Em produção, isso seria gerenciado por sessão
    messages = []
    
    while True:
        user_input = input("Você: ")
        
        if user_input.lower() == "sair":
            break
            
        try:
            VisualLogger.log_user(user_input)
            VisualLogger.log_agent_start()
            
            # Executa o agente
            result = await menux_agent.run(user_input, message_history=messages, deps=deps)
            
            # Atualiza histórico
            messages = result.new_messages()
            
            # Log Visual
            VisualLogger.log_agent_response(result.output.model_dump())
            
        except Exception as e:
            print(f"Erro: {e}")

if __name__ == "__main__":
    if not os.getenv("OPENAI_API_KEY"):
        print("AVISO: OPENAI_API_KEY não encontrada no ambiente. O agente pode falhar se tentar chamar a API real.")
    
    asyncio.run(main())
