"""Explicit launcher for the local SAFE-FIELD heavy-inference worker.

This is intentionally not installed as a Windows service.  Models and the
bearer token are supplied through the process environment and never written to
the repository.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mvp.operational_intelligence.recovery_audio import (
    FROZEN_ASR_BEAM,
    FROZEN_ASR_MODEL,
    FROZEN_ASR_VARIANT,
    FROZEN_DIARIZATION_GAP_SECONDS,
    FROZEN_DIARIZATION_WINDOW_SECONDS,
    FrozenRecoveryASRProvider,
    RecoveryDiarizer,
    enable_cuda_dlls,
)
from mvp.operational_intelligence.razer_worker_transport import (
    WorkerProviders,
    make_razer_worker_server,
)


REPOSITORY = Path(__file__).resolve().parents[1]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="SAFE-FIELD private Razer inference worker")
    result.add_argument("--bind", default="127.0.0.1")
    result.add_argument("--port", type=int, default=8766)
    result.add_argument(
        "--device",
        choices=("cuda",),
        default="cuda",
        help="frozen Baseline B inference device",
    )
    result.add_argument(
        "--models-root",
        type=Path,
        default=Path(
            os.environ.get(
                "SAFE_FIELD_RECOVERY_MODELS_ROOT",
                REPOSITORY / "mvp" / "evidence" / "models",
            )
        ),
        help="local ignored root containing the frozen Baseline B model bundles",
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


def compose_frozen_worker_providers(
    models_root: Path,
) -> tuple[WorkerProviders, dict[str, str]]:
    """Build only the inference providers approved by digital Baseline B."""
    enable_cuda_dlls()
    root = models_root.resolve()
    asr = FrozenRecoveryASRProvider(root)
    diarization = RecoveryDiarizer(
        root,
        gap=FROZEN_DIARIZATION_GAP_SECONDS,
        window=FROZEN_DIARIZATION_WINDOW_SECONDS,
    )
    providers = WorkerProviders(
        asr=asr,
        diarization=diarization,
        embedding=diarization.embedding_provider,
        reasoning=None,
    )
    readiness = {
        "profile": "FROZEN_GOOD_BASELINE",
        "asr": f"{FROZEN_ASR_MODEL}:{FROZEN_ASR_VARIANT}:beam{FROZEN_ASR_BEAM}",
        "asr_runtime": "CUDA_FP16",
        "diarization": (
            "RecoveryDiarizer:"
            f"gap{FROZEN_DIARIZATION_GAP_SECONDS}:"
            f"window{FROZEN_DIARIZATION_WINDOW_SECONDS}"
        ),
        "observation_quality": "REQUIRED",
        "reasoning": "DISABLED_ON_REMOTE_WORKER",
    }
    return providers, readiness


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    token = os.environ.get("SAFE_FIELD_RAZER_WORKER_TOKEN")
    providers, readiness = compose_frozen_worker_providers(args.models_root)
    server = make_razer_worker_server(
        args.bind,
        args.port,
        providers,
        bearer_token=token,
        allow_insecure_private_http=args.allow_insecure_private_http,
        provider_timeout_seconds=args.provider_timeout,
        spool_root=args.spool_root,
        spool_ttl_seconds=args.spool_ttl_hours * 60 * 60,
    )
    readiness_text = ", ".join(f"{name}={state}" for name, state in readiness.items())
    print(f"SAFE-FIELD worker v2 listening on {args.bind}:{server.server_port}; {readiness_text}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
