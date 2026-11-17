"""Import from Paperless-ngx through its REST API.

An administrator enters the Paperless address and an API token, checks the connection and starts
the import. Each page of 25 documents is its own background job, so a large archive is imported
in small steps, can be stopped, and continues where it stopped. Every original file goes through
DocuHive's pipeline like an upload; title, date, correspondent and tags from Paperless are kept as
the person's own values. Nothing is ever changed or deleted in Paperless.
"""

from datetime import date
from typing import Any

from docuhive.sdk import ActionError, Registry, User, documents, http
from sqlalchemy import text

PAGE = 25


class Unreachable(ActionError):
    pass


def setup(registry: Registry) -> None:  # noqa: C901
    def q(sql: str, **params) -> list[dict]:
        with registry.db.session() as s:
            return [dict(r) for r in s.execute(text(sql), params).mappings()]

    def run(sql: str, **params) -> Any:
        with registry.db.session() as s:
            return s.execute(text(sql), params)

    def admin(user: User) -> None:
        if user.role != "admin":
            raise ActionError("Only an administrator can import from Paperless.")

    # Paperless API ----------------------------------------------------------------------------

    def base() -> str:
        url = str(registry.settings.get("url") or "").strip().rstrip("/")
        if not url:
            raise ActionError("Enter the Paperless address under Settings → Plugins first.")
        return url if "://" in url else f"http://{url}"

    def get(path: str, **params: Any) -> Any:
        url = base()
        token = registry.settings.get("token")
        if not token:
            raise ActionError("Enter the Paperless API token under Settings → Plugins first.")
        try:
            with http.client(registry, follow_redirects=True) as c:
                response = c.get(
                    f"{url}{path}", params=params, headers={"Authorization": f"Token {token}"}
                )
        except (http.HTTPError, http.HostNotAllowed) as error:
            raise Unreachable(f"Paperless cannot be reached at {url}: {error}") from None
        if response.status_code in (401, 403):
            raise Unreachable("Paperless refused the token. Copy it again from your profile there.")
        if response.status_code >= 400:
            raise Unreachable(f"Paperless answered {response.status_code} for {path}.")
        return response

    def names(path: str) -> dict[int, str]:
        out: dict[int, str] = {}
        page = 1
        while True:
            data = get(path, page=page, page_size=1000).json()
            out |= {r["id"]: r["name"] for r in data["results"]}
            if not data.get("next"):
                return out
            page += 1

    # Starting and checking --------------------------------------------------------------------

    @registry.action("check")
    def check(user: User, params: dict) -> str:
        admin(user)
        count = get("/api/documents/", page_size=1).json()["count"]
        done = q("SELECT count(*) AS n FROM imported WHERE owner_id = :o", o=user.id)[0]["n"]
        return f"Connected. Paperless has {count} documents; {done} of them are already here."

    def current_run(user: User) -> dict | None:
        rows = q("SELECT * FROM runs WHERE owner_id = :o ORDER BY id DESC LIMIT 1", o=user.id)
        return rows[0] if rows else None

    @registry.action("start")
    def start(user: User, params: dict) -> str:
        admin(user)
        last = current_run(user)
        if last and last["state"] == "running":
            raise ActionError("An import is already running.")
        total = get("/api/documents/", page_size=1).json()["count"]
        with registry.db.session() as s:
            run_id = s.execute(
                text(
                    "INSERT INTO runs (owner_id, state, total) VALUES (:o, 'running', :t) "
                    "RETURNING id"
                ),
                {"o": user.id, "t": total},
            ).scalar_one()
        registry.enqueue(
            "import_page",
            {"run": run_id, "page": 1, "user": user.model_dump(mode="json")},
            dedupe_key=f"{run_id}:1",
        )
        return f"Importing {total} documents in the background. You can leave this page."

    @registry.action("stop")
    def stop(user: User, params: dict) -> str:
        admin(user)
        run(
            "UPDATE runs SET state = 'stopped', finished_at = now() WHERE owner_id = :o AND "
            "state = 'running'",
            o=user.id,
        )
        return "Stopped after the current step. Start again to continue where it stopped."

    # The import itself ------------------------------------------------------------------------

    @registry.job("import_page", timeout_s=1800)
    def import_page(payload: dict, ctx: Any) -> None:
        user = User.model_validate(payload["user"])
        state = q("SELECT state FROM runs WHERE id = :r", r=payload["run"])
        if not state or state[0]["state"] != "running":
            return
        try:
            data = get(
                "/api/documents/", page=payload["page"], page_size=PAGE, ordering="id"
            ).json()
            tags, people = names("/api/tags/"), names("/api/correspondents/")
            types = names("/api/document_types/") if registry.settings.get("type_as_tag") else {}
        except Unreachable as error:
            run(
                "UPDATE runs SET state = 'failed', error = :e, finished_at = now() WHERE id = :r",
                e=str(error),
                r=payload["run"],
            )
            return
        seen = {
            r["paperless_id"]
            for r in q(
                "SELECT paperless_id FROM imported WHERE owner_id = :o AND status <> 'failed'",
                o=user.id,
            )
        }
        for doc in data["results"]:
            if doc["id"] not in seen:
                import_one(user, doc, tags, people, types)
            ctx.heartbeat()
        run(
            "UPDATE runs SET done = (SELECT count(*) FROM imported WHERE owner_id = :o) "
            "WHERE id = :r",
            o=user.id,
            r=payload["run"],
        )
        if data.get("next"):
            registry.enqueue(
                "import_page",
                payload | {"page": payload["page"] + 1},
                dedupe_key=f"{payload['run']}:{payload['page'] + 1}",
            )
        else:
            run(
                "UPDATE runs SET state = 'finished', finished_at = now() WHERE id = :r AND "
                "state = 'running'",
                r=payload["run"],
            )

    def import_one(user: User, doc: dict, tags: dict, people: dict, types: dict) -> None:
        title = doc.get("title") or doc.get("original_file_name") or f"Paperless {doc['id']}"
        try:
            content = get(f"/api/documents/{doc['id']}/download/", original="true").content
            created = str(doc.get("created") or doc.get("created_date") or "")[:10]
            labels = [tags[t] for t in doc.get("tags") or [] if t in tags]
            if doc.get("document_type") in types:
                labels.append(f"paperless:{types[doc['document_type']]}")
            document_id, status = documents.import_file(
                user,
                content,
                filename=doc.get("original_file_name") or f"paperless-{doc['id']}.pdf",
                title=title,
                tags=labels,
                correspondent=people.get(doc.get("correspondent")),
                document_date=date.fromisoformat(created) if created else None,
                analyse=bool(registry.settings.get("analyse")),
            )
            result, error = ("duplicate" if status == "duplicate" else "imported"), None
        except Exception as e:  # noqa: BLE001 - one bad file must not stop the import
            document_id, result, error = None, "failed", f"{type(e).__name__}: {e}"[:500]
        run(
            "INSERT INTO imported (owner_id, paperless_id, document_id, status, error, title) "
            "VALUES (:o, :p, :d, :s, :e, :t) ON CONFLICT (owner_id, paperless_id) DO UPDATE SET "
            "document_id = excluded.document_id, status = excluded.status, error = excluded.error, "
            "at = now()",
            o=user.id,
            p=doc["id"],
            d=document_id,
            s=result,
            e=error,
            t=title,
        )

    # What the page shows ----------------------------------------------------------------------

    @registry.data("progress")
    def progress(user: User, params: dict) -> list[dict]:
        last = current_run(user)
        if last is None:
            return [{"label": "Import", "value": "Not started"}]
        counts = {
            r["status"]: r["n"]
            for r in q(
                "SELECT status, count(*) AS n FROM imported WHERE owner_id = :o GROUP BY status",
                o=user.id,
            )
        }
        return [
            {"label": "Import", "value": last["state"].capitalize()},
            {"label": "In Paperless", "value": last["total"], "format": "number"},
            {"label": "Imported", "value": counts.get("imported", 0), "format": "number"},
            {"label": "Already here", "value": counts.get("duplicate", 0), "format": "number"},
            {"label": "Problems", "value": counts.get("failed", 0), "format": "number"},
        ]

    @registry.data("problems")
    def problems(user: User, params: dict) -> list[dict]:
        last = current_run(user)
        rows = q(
            "SELECT paperless_id, title, error FROM imported WHERE owner_id = :o AND status = "
            "'failed' ORDER BY paperless_id",
            o=user.id,
        )
        if last and last["error"]:
            rows.insert(0, {"paperless_id": None, "title": "The import", "error": last["error"]})
        return rows

    @registry.data("imported_documents")
    def imported_documents(user: User, params: dict) -> list[dict]:
        return q(
            "SELECT paperless_id, title, document_id, status, at FROM imported WHERE owner_id = :o "
            "AND status <> 'failed' ORDER BY at DESC LIMIT 200",
            o=user.id,
        )

    @registry.data("is_running")
    def is_running(user: User, params: dict) -> bool:
        last = current_run(user)
        return bool(last and last["state"] == "running")

    @registry.data("is_idle")
    def is_idle(user: User, params: dict) -> bool:
        return not is_running(user, params)
