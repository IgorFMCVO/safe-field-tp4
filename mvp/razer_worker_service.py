"""Explicit launcher for the local SAFE-FIELD heavy-inference worker.

This is intentionally not installed as a Windows service.  Models and the
bearer token are supplied through the process environment and never written to
the repository.
"""

from __future__ import annotations

import argparse
import os

from mvp.operational_intelligence.grounded_reasoning import LocalGroundedReasoningProvider
from mvp.operational_intelligence.local_ai import build_local_ai_provider_bundle
from mvp.operational_intelligence.razer_worker_transport import (
    WorkerProviders,
    make_razer_worker_server,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="SAFE-FIELD private Razer inference worker")
    result.add_argument("--bind", default="127.0.0.1")
    result.add_argument("--port", type=int, default=8766)
    result.add_argument(
        "--device",
        choices=("cpu", "cuda"),
        default="cpu",
        help="local inference device; CPU is the validated default on this Razer",
    )
    result.add_argument("--provider-timeout", type=float, default=60.0)
    result.add_argument("--spool-root")
    result.add_argument("--spool-ttl-hours", type=float, default=24.0)
    result.add_argument(
        "--allow-insecure-private-http",
        action="store_true",
        help="explicitly accept unencrypted audio/token on a private LAN",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    token = os.environ.get("SAFE_FIELD_RAZER_WORKER_TOKEN")
    bundle = build_local_ai_provider_bundle(device=args.device)
    server = make_razer_worker_server(
        args.bind,
        args.port,
        WorkerProviders(
            asr=bundle.asr,
            diarization=bundle.diarization,
            embedding=bundle.embedding,
            reasoning=LocalGroundedReasoningProvider(),
        ),
        bearer_token=token,
        allow_insecure_private_http=args.allow_insecure_private_http,
        provider_timeout_seconds=args.provider_timeout,
        spool_root=args.spool_root,
        spool_ttl_seconds=args.spool_ttl_hours * 60 * 60,
    )
    readiness = ", ".join(f"{name}={state}" for name, state in bundle.readiness.items())
    print(f"SAFE-FIELD worker v1 listening on {args.bind}:{server.server_port}; {readiness}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
