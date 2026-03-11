from fastapi import APIRouter

from trackforge.api.v1.auth import router as auth_router
from trackforge.api.v1.library import router as library_router
from trackforge.api.v1.requests import router as requests_router
from trackforge.api.v1.review import router as review_router
from trackforge.api.v1.search import router as search_router
from trackforge.api.v1.settings import router as settings_router
from trackforge.api.v1.trending import router as trending_router
from trackforge.api.v1.users import router as users_router

router = APIRouter()

router.include_router(auth_router)
router.include_router(search_router)
router.include_router(requests_router)
router.include_router(review_router)
router.include_router(users_router)
router.include_router(trending_router)
router.include_router(settings_router)
router.include_router(library_router)


@router.get("/ping")
async def ping() -> dict:
    return {"message": "pong"}
