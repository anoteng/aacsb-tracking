from .auth import router as auth_router
from .aol import router as aol_router
from .users import router as users_router
from .admin import router as admin_router
from .research import router as research_router

__all__ = ["auth_router", "aol_router", "users_router", "admin_router", "research_router"]
