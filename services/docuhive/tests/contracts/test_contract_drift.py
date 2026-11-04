"""The documentation's binding models and function signatures must match the real source."""

import ast
import inspect
import re
from importlib import import_module
from pathlib import Path

import pytest
from docuhive import contracts

ROOT = Path(__file__).resolve().parents[4]


def signature(node):
    args = node.args
    return (
        [a.arg for a in args.posonlyargs],
        [a.arg for a in args.args],
        [a.arg for a in args.kwonlyargs],
        [ast.unparse(d) for d in args.defaults],
        [ast.unparse(d) if d else None for d in args.kw_defaults],
        ast.unparse(node.returns) if node.returns else None,
        {
            a.arg: ast.unparse(a.annotation) if a.annotation else None
            for a in [*args.posonlyargs, *args.args, *args.kwonlyargs]
        },
    )


def test_every_model_field_enum_and_version_matches_contract_document():
    text = (ROOT / "docs/shared/contracts.md").read_text()
    code = re.findall(r"```python\n(.*?)```", text, re.S)[0]
    documented = ast.parse(code)
    actual = ast.parse(inspect.getsource(import_module("docuhive.contracts.models")))
    for model in [n for n in documented.body if isinstance(n, ast.ClassDef)]:
        implementation = next(
            n for n in actual.body if isinstance(n, ast.ClassDef) and n.name == model.name
        )
        expected = {
            n.target.id: ast.dump(n, include_attributes=False)
            for n in model.body
            if isinstance(n, ast.AnnAssign)
        }
        fields = {
            n.target.id: ast.dump(n, include_attributes=False)
            for n in implementation.body
            if isinstance(n, ast.AnnAssign)
        }
        assert expected == fields, model.name
        if model.name in {"SourceKind", "DocStatus"}:
            assert [ast.dump(n) for n in model.body if isinstance(n, ast.Assign)] == [
                ast.dump(n) for n in implementation.body if isinstance(n, ast.Assign)
            ]
    assert contracts.CONTRACT_VERSION == 1


@pytest.mark.parametrize(
    "section,module",
    [
        ("2.1 Config", "docuhive.config"),
        ("2.2 Database", "docuhive.db"),
        ("2.3 Jobs", "docuhive.jobs"),
        ("2.4 Ingest", "docuhive.ingest"),
        ("2.5 Documents", "docuhive.documents"),
        ("2.6 Auth", "docuhive.auth"),
        ("2.7 Search", "docuhive.search"),
    ],
)
def test_public_function_signatures_match_document(section, module):
    text = (ROOT / "docs/shared/contracts.md").read_text().split(f"### {section}", 1)[1]
    code = re.search(r"```python\n(.*?)```", text, re.S)[1]
    implementation = import_module(module)
    for function in [n for n in ast.parse(code).body if isinstance(n, ast.FunctionDef)]:
        real = getattr(implementation, function.name)
        actual = next(
            n for n in ast.parse(inspect.getsource(real)).body if isinstance(n, ast.FunctionDef)
        )
        if any(isinstance(d, ast.Name) and d.id == "contextmanager" for d in actual.decorator_list):
            assert ast.unparse(actual.returns) == "Iterator[Session]"
            actual.returns = ast.parse("ContextManager[Session]", mode="eval").body
        assert signature(function) == signature(actual), f"{module}.{function.name}"
