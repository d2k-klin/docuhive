"""Shared category choices for manual metadata and automatic classification."""

import re
import unicodedata
from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

from docuhive import config, taxonomy
from docuhive.ai.http import Admin, User, fail
from docuhive.contracts import Category

router = APIRouter(prefix="/api", tags=["taxonomy"])


@router.get("/taxonomy")
def get_taxonomy(user: User) -> dict:
    tax = taxonomy.load()
    return tax.model_dump() | {
        "tree": taxonomy.tree(tax.categories),
        "preset_ids": [c.id for c in taxonomy.defaults().categories],
    }


class CategoryChoices(BaseModel):
    enabled_ids: list[str] = Field(max_length=500)


@router.put("/taxonomy/categories")
def choose_categories(body: CategoryChoices, user: Admin) -> dict:
    tax = taxonomy.load()
    ids = {c.id for c in tax.categories}
    enabled = set(body.enabled_ids)
    if enabled - ids:
        fail(
            422,
            "category_unknown",
            "One of these categories no longer exists. Reload and try again.",
        )
    if "other" in ids:
        enabled.add("other")
    for category in list(enabled):
        parts = category.split("/")
        enabled.update("/".join(parts[:i]) for i in range(1, len(parts)))
    if not enabled:
        fail(422, "category_required", "Choose at least one category for your documents.")
    config.set_setting(
        "taxonomy.categories",
        [c.model_copy(update={"enabled": c.id in enabled}).model_dump() for c in tax.categories],
    )
    return get_taxonomy(user)


class CustomCategory(BaseModel):
    label: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=400)
    parent_id: str | None = None
    restricted: bool = False


@router.post("/taxonomy/categories")
def create_category(body: CustomCategory, user: Admin) -> dict:
    tax = taxonomy.load()
    label = " ".join(body.label.split())
    if not label:
        fail(422, "category_name_required", "Give your category a name.")
    if len(tax.categories) >= 500:
        fail(422, "category_limit", "You can have up to 500 categories. Use an existing category.")
    if body.parent_id and not any(c.id == body.parent_id and c.enabled for c in tax.categories):
        fail(422, "category_parent_unknown", "Choose an enabled parent category, or no parent.")
    slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode().lower(),
    ).strip("-")
    slug = slug or f"custom-{uuid4().hex[:8]}"
    category_id = f"{body.parent_id}/{slug}" if body.parent_id else slug
    if any(c.id == category_id for c in tax.categories):
        fail(
            409,
            "category_exists",
            "A category with this name already exists here. Choose it from the list.",
        )
    tax.categories.append(
        Category(
            id=category_id,
            label=label,
            description=body.description.strip(),
            restricted=body.restricted,
        )
    )
    taxonomy.validate(tax.model_dump())
    config.set_setting("taxonomy.categories", [c.model_dump() for c in tax.categories])
    return get_taxonomy(user)
