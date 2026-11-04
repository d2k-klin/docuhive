import argparse
from pathlib import Path

import pytest
from docuhive_evals import report, scorers
from docuhive_evals.datasets import DatasetError, load_labels

SYNTHETIC = Path(__file__).resolve().parents[4] / "evals" / "synthetic"


def test_scorers_hand_computed():
    assert scorers.accuracy([(1, 1), (1, 2), (3, 3), (4, 4)]) == 0.75
    assert scorers.tag_prf([(["a", "b"], ["a"]), ([], ["c"])]) == {
        "precision": 0.5,
        "recall": 0.5,
        "f1": 0.5,
    }
    assert scorers.calibration([(True, 0.9, 0.8), (False, 0.85, 0.8), (True, 0.5, 0.8)]) == {
        "precision_above_threshold": 0.5,
        "share_above_threshold": 0.667,
    }
    assert scorers.fact_equal(
        {"value": "84.20", "currency": "EUR"}, {"value": "84.20", "currency": "EUR"}
    )
    assert not scorers.fact_equal(
        {"value": "84.20", "currency": "EUR"}, {"value": "84.20", "currency": "CHF"}
    )
    assert scorers.correspondent_match(
        "Stadtwerke Musterstadt", "Stadtwerke Musterstadt GmbH", fuzzy=True
    )
    assert not scorers.correspondent_match(
        "Stadtwerke Musterstadt", "Stadtwerke Musterstadt GmbH", fuzzy=False
    )
    assert scorers.parent("utilities/electricity") == "utilities"
    assert scorers.latency([10, 20, 30, 40]) == {"p50": 25.0, "p95": 40}


def test_dataset_errors_are_readable(tmp_path):
    (tmp_path / "labels.yaml").write_text("- id: x\n  file: docs/x.txt\n  expect: {category: a}\n")
    with pytest.raises(DatasetError, match=r"entry x: expect.document_type: Field required"):
        load_labels(tmp_path)
    (tmp_path / "labels.yaml").write_text(
        "- id: y\n  file: docs/missing.txt\n"
        "  expect: {category: a, document_type: b, language: de}\n"
    )
    with pytest.raises(DatasetError, match="file docs/missing.txt not found"):
        load_labels(tmp_path)


def test_synthetic_set_is_consistent(core):
    from docuhive import taxonomy

    cases = load_labels(SYNTHETIC)
    tax = taxonomy.load()
    assert len(cases) == 40 and {c.expect.language for c in cases} == {"de", "en"}
    assert {c.expect.category for c in cases} <= {c.id for c in tax.categories}
    assert {c.expect.document_type for c in cases} <= {t.id for t in tax.document_types}
    assert any(c.restricted for c in cases)


def test_cli_smoke_with_fake_models(core, tmp_path, capsys):
    from docuhive_evals.cli import register

    out_dir = tmp_path / "reports"
    root = argparse.ArgumentParser()
    register(root.add_subparsers(dest="command"))
    for task in ("classify", "extract"):
        args = root.parse_args(
            [
                "eval",
                task,
                "--set",
                str(SYNTHETIC),
                "--limit",
                "5",
                "--route",
                f"{task}=fake/oracle",
                "--route",
                f"{task}=fake/noisy",
                "--out",
                str(out_dir),
            ]
        )
        args.func(args)
    out = capsys.readouterr().out
    assert "| metric | `fake/oracle` | `fake/noisy` |" in out and "gate fake/oracle: PASS" in out
    assert sorted(p.suffix for p in out_dir.iterdir()) == [".json", ".json", ".md", ".md"]


def test_search_eval_on_fakes(core):
    from docuhive_evals.datasets import load_yaml_list
    from docuhive_evals.retrieval import search_set

    res = search_set(
        load_labels(SYNTHETIC), load_yaml_list(SYNTHETIC, "search.yaml"), "fake/embed", "semantic"
    )
    assert res["recall_at_k"] > 0.5 and res["queries"] == 8


def test_gate():
    assert report.gate(
        {
            "precision_above_threshold": 0.96,
            "category_accuracy": 0.91,
            "document_type_accuracy": 0.95,
        }
    )
    assert not report.gate(
        {
            "precision_above_threshold": 0.96,
            "category_accuracy": 0.89,
            "document_type_accuracy": 0.95,
        }
    )
