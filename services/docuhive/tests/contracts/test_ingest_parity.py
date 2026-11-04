"""File ownership, synchronous rejection and per-owner dedupe for real and fake ingest."""

import pytest
from docuhive import ingest
from docuhive.auth import create_user
from docuhive.contracts import IngestRequest, SourceInfo, SourceKind
from docuhive.ingest import UnsupportedType
from ulid import ULID


@pytest.fixture(
    params=[
        "fake",
        pytest.param(
            "real",
            marks=[
                pytest.mark.integration,
                pytest.mark.xfail(
                    strict=True,
                    raises=NotImplementedError,
                    reason="I4/OA-M3: docs/Developer-QA/bugs.md#qa-001",
                ),
            ],
        ),
    ]
)
def ingress(request):
    if request.param == "fake":
        return request.getfixturevalue("fake_core").ingest, 1, 2
    request.getfixturevalue("postgres")
    owners = [create_user(name, "synthetic qa password 2026") for name in ("qa-a", "qa-b")]
    return ingest, *owners


@pytest.mark.req("ING-05")
def test_input_ownership_duplicate_identity_and_owner_isolation(ingress):
    backend, owner, other = ingress
    root = backend.incoming_dir()
    path = root / "synthetic.pdf"
    source = SourceInfo(kind=SourceKind.upload, original_filename=path.name)
    ids = []
    for account in (owner, owner, other):
        path.write_bytes(b"%PDF-1.4\nsynthetic QA-DOC:case-001")
        result = backend.submit([path], IngestRequest(owner_id=account, source=source))
        assert str(ULID.from_str(result.document_id)) == result.document_id
        assert not path.exists()
        ids.append(result.document_id)
        assert result.status == ("duplicate" if len(ids) == 2 else "staged")
    assert ids[0] == ids[1] != ids[2]


@pytest.mark.req("ING-02", "ING-04")
def test_rejected_input_is_not_consumed(ingress):
    backend, owner, _ = ingress
    path = backend.incoming_dir() / "unsupported.bin"
    path.write_bytes(b"\x00\x01\x02\x03")
    with pytest.raises(UnsupportedType):
        backend.submit(
            [path],
            IngestRequest(
                owner_id=owner,
                source=SourceInfo(kind=SourceKind.upload, original_filename=path.name),
            ),
        )
    assert path.read_bytes() == b"\x00\x01\x02\x03"
