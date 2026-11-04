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
