from app.api.routes.auth import router as auth_router
from app.api.routes.bots import router as bots_router
from app.api.routes.chat import router as chat_router
from app.api.routes.crawl import router as crawl_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.widget import router as widget_router

__all__ = ["auth_router", "bots_router", "chat_router", "crawl_router", "knowledge_router", "widget_router"]
