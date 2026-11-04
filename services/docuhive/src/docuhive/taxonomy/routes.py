"""GET /api/taxonomy: the taxonomy plus a category tree for pickers and filters."""

from fastapi import APIRouter

from docuhive import taxonomy
from docuhive.ai.http import User

router = APIRouter(prefix="/api", tags=["taxonomy"])


@router.get("/taxonomy")
def get_taxonomy(user: User) -> dict:
    tax = taxonomy.load()
    return tax.model_dump() | {"tree": taxonomy.tree(tax.categories)}
