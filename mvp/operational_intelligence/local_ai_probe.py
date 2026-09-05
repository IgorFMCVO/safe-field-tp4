"""Print a redacted JSON inventory of local inference readiness."""

from __future__ import annotations

import json

from .local_ai import build_local_ai_provider_bundle, probe_local_ai_runtime


def main() -> int:
    probe = probe_local_ai_runtime()
    bundle = build_local_ai_provider_bundle()
    output = probe.to_dict()
    output["readiness"] = dict(bundle.readiness)
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
