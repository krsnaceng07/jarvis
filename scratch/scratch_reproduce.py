import asyncio
import traceback

async def main():
    try:
        from src.agents.sessions.sdk import create_agent_session
        result = await create_agent_session()
        session = result["session"]
        
        class MockModel:
            id = "models/gemini-3.1-flash-live-preview"
            provider = "google"
        session.model = MockModel()
        
        class MockRegistry:
            def has_configured_auth(self, model):
                return True
        session.session_model_registry = MockRegistry()
        
        class MockApi:
            _hooks = None
        session.api = MockApi()
        await session.prompt("hello")
    except Exception:
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
