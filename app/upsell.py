from typing import Dict, Any, Optional
from app.models import UpsellData, UpsellType

class UpsellManager:
    @staticmethod
    async def check_upsell(
        recommended_ids: list[str], 
        menu_cache: Dict[str, Dict[str, Any]]
    ) -> Optional[UpsellData]:
        """
        Verifica se o primeiro item recomendado tem upsell configurado.
        Retorna o objeto UpsellData ou None.
        """
        if not recommended_ids or not menu_cache:
            return None
        
        # Foca no primeiro item (Hero)
        main_item_id = recommended_ids[0]
        main_item = menu_cache.get(main_item_id)
        
        if not main_item:
            return None
            
        upsell_list = main_item.get("upsellItems", [])
        if not upsell_list:
            return None
            
        # Pega a primeira regra de upsell disponível
        rule = upsell_list[0]
        
        u_type_str = rule.get("upsellType", "cross-sell")
        target_id = rule.get("upgradeProductId")
        
        if not target_id:
            return None
            
        # Tenta pegar o nome do item alvo no cache para personalizar a mensagem
        target_item = menu_cache.get(target_id)
        target_name = target_item.get("name") if target_item else "uma opção especial"
        
        u_type = UpsellType.CROSS_SELL
        message = ""
        
        if u_type_str == "cross-sell":
            u_type = UpsellType.CROSS_SELL
            message = f"Sugestão do Chef: Que tal adicionar {target_name} para acompanhar?"
        else:
            u_type = UpsellType.UPSELL
            message = f"Dica: Experimente dar um upgrade para {target_name}!"
            
        return UpsellData(
            type=u_type,
            message=message,
            items=[target_id]
        )
