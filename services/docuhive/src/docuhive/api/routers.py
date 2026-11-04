"""Shared touchpoint: append routers without removing existing registrations."""

from fastapi import APIRouter

from .system import router as system_router

ROUTERS: list[APIRouter] = [system_router]

from .auth import router as auth_router  # noqa: E402

ROUTERS.append(auth_router)

from .users import router as users_router  # noqa: E402

ROUTERS.append(users_router)

from docuhive.ai.routers import CL_ROUTERS  # noqa: E402  (CL: taxonomy, ai, review, sources, chat, ...)

ROUTERS.extend(CL_ROUTERS)

from .knowledge import router as knowledge_router  # noqa: E402

ROUTERS.append(knowledge_router)

from .duplicates import router as duplicates_router  # noqa: E402
from .export import router as export_router  # noqa: E402
from .fields import router as fields_router  # noqa: E402
from .views import router as views_router  # noqa: E402

ROUTERS.extend([fields_router, views_router, duplicates_router, export_router])

from .documents import router as documents_router  # noqa: E402
from .upload import router as upload_router  # noqa: E402

ROUTERS.extend([documents_router, upload_router])

from .vocabulary import router as vocabulary_router  # noqa: E402

ROUTERS.append(vocabulary_router)
