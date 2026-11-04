"""Catch direct cross-track SQL writes; read-only shared-table access is allowed."""

import ast
import re

import pytest
from qa_plugin import ROOT

CORE = {
    "documents",
    "tags",
    "document_tags",
    "correspondents",
    "doc_facts",
    "doc_sources",
    "notes",
    "users",
    "sessions",
    "api_tokens",
    "audit_log",
    "settings",
    "jobs",
}
INTEL = {
    "mail_accounts",
    "mail_messages",
    "mail_attachments",
    "backfills",
    "ai_runs",
    "review_items",
    "doc_chunks",
    "chat_sessions",
    "chat_messages",
    "analyses",
    "reminders",
    "notification_channels",
    "notification_log",
}
CL = {"ai", "agents", "mail", "taxonomy", "review", "index", "chat", "reminders", "notify"}


def write_violations(source: str, forbidden: set[str]) -> list[int]:
    tree = ast.parse(source)
    aliases = {
        a.asname or a.name: a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom)
        for a in n.names
    }
    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            names = re.findall(
                r'\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+["\[]?(\w+)', node.value, re.I
            )
            if forbidden & {name.lower() for name in names}:
                violations.append(node.lineno)
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        if (
            isinstance(fn, ast.Name)
            and aliases.get(fn.id, fn.id) in {"insert", "update", "delete"}
            and node.args
        ):
            target = ast.unparse(node.args[0]).split(".")[-1]
        elif isinstance(fn, ast.Attribute) and fn.attr in {"insert", "update", "delete"}:
            target = ast.unparse(fn.value).split(".")[-1]
        else:
            continue
        name = aliases.get(target, target)
        snake = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()
        candidates = {snake, snake + "s", "documents" if name == "Document" else snake}
        if candidates & forbidden:
            violations.append(node.lineno)
    return sorted(set(violations))


def test_write_detector_handles_raw_sql_core_orm_and_aliases():
    for code in [
        'db.execute(text("UPDATE documents SET title=:title"))',
        "ct.documents.update().values(title='x')",
        "from sqlalchemy import insert as put\nput(documents)",
        "from docuhive.db.models import Document as D\nupdate(D)",
    ]:
        assert write_violations(code, CORE)
    assert not write_violations("select(documents).where(documents.c.id == 'x')", CORE)


@pytest.mark.req("QAR-INT-03")
def test_no_cross_track_table_writes():
    violations = []
    root = ROOT / "services/docuhive/src/docuhive"
    for path in root.rglob("*.py"):
        track = path.relative_to(root).parts[0]
        if track == "contracts":
            continue
        lines = write_violations(path.read_text(), CORE if track in CL else INTEL)
        violations.extend(f"{path.relative_to(ROOT)}:{line}" for line in lines)
    assert not violations, "\n".join(violations)
