"""The Mr.D brand files match their manifest and stay small."""

import hashlib
import json
from pathlib import Path

BRAND = Path(__file__).resolve().parents[2] / "assets" / "brand"


def test_brand_files_match_manifest_and_size_budget():
    manifest = json.loads((BRAND / "manifest.json").read_text())["files"]
    images = {path.name for path in BRAND.glob("*.webp")}
    assert images == set(manifest), "every image is listed in the manifest, and only those"
    for name, entry in manifest.items():
        assert hashlib.sha256((BRAND / name).read_bytes()).hexdigest() == entry["sha256"], name
    assert sum((BRAND / name).stat().st_size for name in manifest) < 2 * 1024 * 1024
