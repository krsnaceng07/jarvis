from typing import Any, Dict, Optional


class HonchoClient:
    """Mock client for honcho API."""

    def __init__(self, api_key: str, workspace_id: str, base_url: str):
        self.api_key = api_key
        self.workspace_id = workspace_id
        self.base_url = base_url

    async def get_context(self) -> Dict[str, Any]:
        return {"context": "Mock Honcho Context"}

    async def search_conclusions(self, query: str) -> list[Dict[str, Any]]:
        return [{"conclusion": f"Mock conclusion for {query}"}]

    async def search_messages(
        self, query: str, sender: Optional[str] = None, date: Optional[str] = None
    ) -> list[Dict[str, Any]]:
        return [{"message": f"Mock message matching {query}"}]

    async def get_session(self) -> Dict[str, Any]:
        return {"session_history": "Mock session history", "summary": "Mock summary"}

    async def ask(self, question: str, depth: str) -> str:
        return f"Mock answer to {question} at depth {depth}"

    async def observe_turn(self, turn_data: Dict[str, Any]) -> None:
        pass  # mock upload of turn data
