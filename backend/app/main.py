
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.audit import router as audit_router
from app.api.routes.auth import router as auth_router
from app.api.routes.bids import router as bids_router
from app.api.routes.lots import router as lots_router
from app.api.routes.wallet import router as wallet_router
from app.core.config import settings


app = FastAPI(
    title="Casa de Leilões Verzel",
    description="API para gerenciamento de lotes e leilões online.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(lots_router)
app.include_router(bids_router)
app.include_router(audit_router)
app.include_router(wallet_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "application": "Casa de Leilões Verzel",
    }
