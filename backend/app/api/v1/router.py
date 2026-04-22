from fastapi import APIRouter

from app.api.v1.endpoints import documents, favorites, health, history, metrics, qa, search

api_router = APIRouter()
api_router.include_router(documents.router)
api_router.include_router(search.router)
api_router.include_router(qa.router)
api_router.include_router(history.router)
api_router.include_router(favorites.router)
api_router.include_router(health.router)
api_router.include_router(metrics.router)
