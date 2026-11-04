"""All CL routers, appended to docuhive.api.routers.ROUTERS (shared touchpoint)."""

from docuhive.ai.routes import router as ai_router
from docuhive.chat.routes import analyses_router
from docuhive.chat.routes import router as chat_router
from docuhive.index.routes import router as similar_router
from docuhive.mail.routes import router as sources_router
from docuhive.notify.routes import router as notify_router
from docuhive.reminders.routes import router as reminders_router
from docuhive.review.routes import router as review_router
from docuhive.taxonomy.routes import router as taxonomy_router

CL_ROUTERS = [
    taxonomy_router,
    ai_router,
    similar_router,
    review_router,
    sources_router,
    chat_router,
    analyses_router,
    reminders_router,
    notify_router,
]
