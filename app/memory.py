import json
import os
import redis.asyncio as redis
from typing import List, Optional
from pydantic_ai import ModelMessage
from pydantic import TypeAdapter

# Adapter para serializar/deserializar lista de mensagens do PydanticAI
msg_list_adapter = TypeAdapter(List[ModelMessage])

class RedisMemory:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379")
        self.client = redis.from_url(self.redis_url, decode_responses=True)
        self.ttl = 86400  # 24 horas de expiração

    async def get_history(self, session_id: str) -> List[ModelMessage]:
        """Recupera histórico da sessão do Redis."""
        key = f"menux:chat:{session_id}"
        data = await self.client.get(key)
        if not data:
            return []
        
        try:
            # Reconstrói objetos Pydantic a partir do JSON
            messages = msg_list_adapter.validate_json(data)
            
            # Validação de integridade do histórico (recuperação de erros antigos)
            # Se a primeira mensagem for um ToolReturn sem um ToolCall antes (histórico quebrado legado)
            if messages:
                primeiro_tipo = messages[0].__class__.__name__
                if primeiro_tipo == 'ModelResponse':
                    part_types = [p.__class__.__name__ for p in getattr(messages[0], 'parts', [])]
                    # Se a primeira coisa da memória for a resposta de uma tool (legado quebrado)
                    if 'ToolReturnPart' in part_types:
                        print(f"⚠️ Histórico corrompido detectado para {session_id}. Limpando memória para evitar crash 400.")
                        await self.clear_history(session_id)
                        return []
                        
            return messages
        except Exception as e:
            print(f"Erro ao deserializar histórico: {e}")
            return []

    async def save_history(self, session_id: str, new_messages: List[ModelMessage]):
        """
        Adiciona novas mensagens e trunca para manter apenas as últimas 8.
        NOTA: A lógica aqui carrega tudo, anexa e salva. 
        O ideal em produção seria usar LISTAS do Redis (RPUSH + LTRIM), 
        mas serializar JSON complexo do PydanticAI em strings individuais pode ser chato.
        Vamos simplificar salvando o blob inteiro por enquanto.
        """
        key = f"menux:chat:{session_id}"
        
        # 1. Carrega atual
        current_history = await self.get_history(session_id)
        
        # 2. Anexa novos
        updated_history = current_history + new_messages
        
        # 3. Trunca (Mantém as últimas 8 mensagens de forma segura)
        # Se cortarmos cegamente os últimos N, podemos separar um ToolReturn de um ToolCall,
        # o que gera o erro da OpenAI 'messages.[0].role = tool'.
        max_messages = 8
        if len(updated_history) > max_messages:
            safe_idx = len(updated_history) - max_messages
            # Procura a próxima mensagem segura (ModelRequest do usuário)
            while safe_idx < len(updated_history):
                msg = updated_history[safe_idx]
                # Se for requisição do usuário (ModelRequest)
                if msg.__class__.__name__ == 'ModelRequest':
                    part_types = [p.__class__.__name__ for p in getattr(msg, 'parts', [])]
                    # Paramos se contém a fala do usuário e NÃO for um retorno de tool
                    if 'UserPromptPart' in part_types and 'ToolReturnPart' not in part_types:
                        break
                safe_idx += 1
            
            # Corta a partir do índice seguro encontrado
            updated_history = updated_history[safe_idx:]
            
        # 4. Salva com TTL
        json_data = msg_list_adapter.dump_json(updated_history)
        await self.client.set(key, json_data, ex=self.ttl)
        
    async def clear_history(self, session_id: str):
        key = f"menux:chat:{session_id}"
        await self.client.delete(key)
