"""Fuse synthetic word and meaning candidates: no database, provider or network."""

from docuhive.search import rrf


def main() -> None:
    word_matches = ["invoice-number", "electricity-bill", "contract"]
    meaning_matches = ["electricity-bill", "annual-statement"]
    hits = rrf(word_matches, meaning_matches)
    assert hits[0][0] == "electricity-bill"
    assert hits[0][2] == [2, 1]
    assert abs(hits[0][1] - (1 / 62 + 1 / 61)) < 1e-12
    print("Hybrid ranking (word rank, meaning rank):")
    for document_id, score, ranks in hits:
        print(f"  {document_id}: {score:.5f}, {ranks}")
    assert [item for item, *_ in rrf(word_matches, [])] == word_matches


if __name__ == "__main__":
    main()
