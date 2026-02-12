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
            return msg_list_adapter.validate_json(data)
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
        
        # 3. Trunca (Mantém os últimos 8)
        # Se tiver mais que 8, pega os últimos 8
        if len(updated_history) > 8:
            updated_history = updated_history[-8:]
            
        # 4. Salva com TTL
        json_data = msg_list_adapter.dump_json(updated_history)
        await self.client.set(key, json_data, ex=self.ttl)
        
    async def clear_history(self, session_id: str):
        key = f"menux:chat:{session_id}"
        await self.client.delete(key)
