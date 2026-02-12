import json
from datetime import datetime

class VisualLogger:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    @staticmethod
    def log_user(message: str):
        print(f"\n{VisualLogger.OKBLUE}👤 [USER] {datetime.now().strftime('%H:%M:%S')}{VisualLogger.ENDC}")
        print(f"   {message}")

    @staticmethod
    def log_agent_start():
        print(f"{VisualLogger.HEADER}🤖 [AGENT] Pensando...{VisualLogger.ENDC}")

    @staticmethod
    def log_tool_call(tool_name: str, params: dict):
        print(f"\n{VisualLogger.WARNING}🛠️  [TOOL CALL] {tool_name}{VisualLogger.ENDC}")
        print(f"   Input: {json.dumps(params, indent=2, ensure_ascii=False)}")

    @staticmethod
    def log_tool_result(result: any, success: bool = True):
        color = VisualLogger.OKGREEN if success else VisualLogger.FAIL
        icon = "✅" if success else "❌"
        # Tenta formatar se for objeto pydantic ou dict
        try:
            if hasattr(result, 'model_dump'):
                content = json.dumps(result.model_dump(), indent=2, ensure_ascii=False)
            elif isinstance(result, (dict, list)):
                content = json.dumps(result, indent=2, ensure_ascii=False)
            else:
                content = str(result)
        except:
            content = str(result)

        print(f"{color}{icon} [TOOL RESULT] {len(content)} chars{VisualLogger.ENDC}")
        # Truncar visualização se for muito grande
        if len(content) > 1000:
             print(f"   {content[:1000]}... [truncated]")
        else:
             print(f"   {content}")

    @staticmethod
    def log_agent_response(response: dict):
        print(f"\n{VisualLogger.OKCYAN}✨ [FINAL RESPONSE] {datetime.now().strftime('%H:%M:%S')}{VisualLogger.ENDC}")
        print(f"   {json.dumps(response, indent=2, ensure_ascii=False)}\n")
