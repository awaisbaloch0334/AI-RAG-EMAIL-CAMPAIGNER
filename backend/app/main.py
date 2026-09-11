from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes.auth import router as auth_router
from app.api.routes.bots import router as bots_router
from app.api.routes.campaigns import router as campaigns_router
from app.api.routes.chat import router as chat_router
from app.api.routes.contacts import router as contacts_router
from app.api.routes.crawl import router as crawl_router
from app.api.routes.email import router as email_router
from app.api.routes.hubspot_oauth import router as hubspot_oauth_router
from app.api.routes.knowledge import router as knowledge_router
from app.api.routes.widget import router as widget_router

app = FastAPI(
    title="Embeddable RAG Chatbot API",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(bots_router)
app.include_router(campaigns_router)
app.include_router(contacts_router)
app.include_router(hubspot_oauth_router)
app.include_router(email_router)
app.include_router(crawl_router)
app.include_router(knowledge_router)
app.include_router(chat_router)
app.include_router(widget_router)

# Mount static files directory for widget.js and chat iframe assets
static_dir = Path(__file__).resolve().parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


@app.get("/health")
async def health_check():
    return {"status": "ok"}