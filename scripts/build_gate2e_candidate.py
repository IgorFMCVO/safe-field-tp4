"""Apply the SHA-256-pinned candidate patch in an isolated checkout only.

This script does not contact devices, deploy services or alter runtime data.
It is intentionally limited to the presentation candidate branch in CI.
"""
from __future__ import annotations

import base64
import hashlib
import json
import lzma
from pathlib import Path, PurePosixPath
import re
import subprocess
import tempfile

EXPECTED_SHA256 = "757b95f9c52a80cfcfbc8cb229272bb0f1a908ccea8271fc3ba7d23d8d0426e1"
EXPECTED_LENGTH = 114385


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    pieces = [root / "scripts" / f"gate2e_candidate_payload.{i:02d}.b64" for i in range(4)]
    encoded = "".join("".join(p.read_text(encoding="ascii").split()) for p in pieces)
    patch = lzma.decompress(base64.b64decode(encoded, validate=True))
    if len(patch) != EXPECTED_LENGTH or hashlib.sha256(patch).hexdigest() != EXPECTED_SHA256:
        raise RuntimeError("Candidate payload failed SHA-256/length verification")
    paths = re.findall(r"^\+\+\+ b/(.+)$", patch.decode("utf-8"), re.MULTILINE)
    if len(paths) != 18 or len(set(paths)) != 18:
        raise RuntimeError("Unexpected candidate file manifest")
    for name in paths:
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or not name.startswith(("mvp/", "wearable/", "scripts/open_safe_field_review")):
            raise RuntimeError(f"Unexpected candidate path: {name}")
    out = root / ".build" / "validation"
    out.mkdir(parents=True, exist_ok=True)
    patch_path = out / "GATE2E_CANDIDATE.patch"
    patch_path.write_bytes(patch)
    reverse = subprocess.run(["git", "apply", "--reverse", "--check", str(patch_path)], cwd=root, capture_output=True)
    if reverse.returncode:
        subprocess.run(["git", "apply", "--check", str(patch_path)], cwd=root, check=True)
        subprocess.run(["git", "apply", str(patch_path)], cwd=root, check=True)
        result = "APPLIED"
    else:
        result = "ALREADY_APPLIED"
    manifest = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in paths}
    (out / "source_files.json").write_text(json.dumps(paths, indent=2), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps({"patch_sha256": EXPECTED_SHA256, "result": result, "files": manifest, "physical_validation": "NOT_EXECUTED"}, indent=2), encoding="utf-8")
    print(f"Candidate {result}: {len(paths)} source files, SHA-256 verified")


if __name__ == "__main__":
    main()
