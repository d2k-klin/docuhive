"""FakeModels for the CI smoke run: they answer from the labels, so the machinery is tested
without a real model. `fake/oracle` is always right; `fake/noisy` is wrong on every 4th case."""

from docuhive.ai.fake import FakeModel

from docuhive_evals.datasets import Case


def _case(cases: list[Case], prompt: str) -> Case:
    """The case whose document text is in the prompt (synthetic texts fit the context)."""
    return next(
        (c for c in cases if c.text.strip() in prompt),
        max(cases, key=lambda c: sum(ln in prompt for ln in c.text.splitlines() if ln)),
    )


def classify_fakes(cases: list[Case]) -> dict[str, FakeModel]:
    def answer(prompt: str, noisy: bool) -> dict:
        c = _case(cases, prompt)
        e = c.expect
        wrong = noisy and cases.index(c) % 4 == 0
        return {
            "title": c.id,
            "category": "other" if wrong else e.category,
            "document_type": e.document_type,
            "correspondent": e.correspondent,
            "tags": e.tags,
            "document_date": e.document_date.isoformat() if e.document_date else None,
            "language": e.language,
            "confidence": {
                f: 0.6 if wrong else 0.95
                for f in (
                    "title",
                    "category",
                    "document_type",
                    "correspondent",
                    "tags",
                    "document_date",
                    "language",
                )
            },
        }

    return {
        "fake/oracle": FakeModel(outputs={"*": lambda p: answer(p, False)}),
        "fake/noisy": FakeModel(outputs={"*": lambda p: answer(p, True)}),
    }


def extract_fakes(cases: list[Case]) -> dict[str, FakeModel]:
    def answer(prompt: str, noisy: bool) -> dict:
        c = _case(cases, prompt)
        out = {}
        for name, v in c.expect.facts.items():
            value = v["value"] if isinstance(v, dict) else v
            if noisy and cases.index(c) % 4 == 0:
                value = None
            out[name] = {
                "value": value,
                "confidence": 0.95,
                **({"currency": v.get("currency")} if isinstance(v, dict) else {}),
            }
        return out

    return {
        "fake/oracle": FakeModel(outputs={"*": lambda p: answer(p, False)}),
        "fake/noisy": FakeModel(outputs={"*": lambda p: answer(p, True)}),
    }
