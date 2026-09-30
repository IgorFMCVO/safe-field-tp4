"""Explicit launcher for the local SAFE-FIELD heavy-inference worker.

This is intentionally not installed as a Windows service.  Models and the
bearer token are supplied through the process environment and never written to
the repository.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from mvp.operational_intelligence.diarization_engines import (
    COMMUNITY1_REVISION,
    Community1DiarizerAdapter,
    DiarizationProviderBridge,
)
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
GATE2C_ROOT = Path(r"C:\SAFE-FIELD\_checkpoints\gate2c_ab_20260930T002124Z_3a68721c")
DEFAULT_COMMUNITY1_PYTHON = GATE2C_ROOT / "community1_venv" / "Scripts" / "python.exe"
DEFAULT_COMMUNITY1_CACHE_ROOT = GATE2C_ROOT / "community1_cache"
DEFAULT_COMMUNITY1_SNAPSHOT = (
    DEFAULT_COMMUNITY1_CACHE_ROOT
    / "models--pyannote--speaker-diarization-community-1"
    / "snapshots"
    / COMMUNITY1_REVISION
)


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
    result.add_argument(
        "--diarization-engine",
        choices=("recovery", "community1"),
        default=os.environ.get("DIARIZATION_ENGINE", "recovery").strip().lower(),
        help="explicit diarization engine; Recovery remains the rollback",
    )
    result.add_argument(
        "--community1-python",
        type=Path,
        default=Path(os.environ.get("SAFE_FIELD_COMMUNITY1_PYTHON", DEFAULT_COMMUNITY1_PYTHON)),
        help="isolated offline Community-1 Python runtime",
    )
    result.add_argument(
        "--community1-cache-root",
        type=Path,
        default=Path(
            os.environ.get("SAFE_FIELD_COMMUNITY1_CACHE_ROOT", DEFAULT_COMMUNITY1_CACHE_ROOT)
        ),
        help="local Community-1 Hugging Face cache (offline only)",
    )
    result.add_argument(
        "--community1-model-snapshot",
        type=Path,
        default=Path(
            os.environ.get("SAFE_FIELD_COMMUNITY1_MODEL_SNAPSHOT", DEFAULT_COMMUNITY1_SNAPSHOT)
        ),
        help="pinned local Community-1 snapshot",
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
    *,
    diarization_engine: str = "recovery",
    community1_python: Path | None = None,
    community1_cache_root: Path | None = None,
    community1_model_snapshot: Path | None = None,
) -> tuple[WorkerProviders, dict[str, str]]:
    """Build only the inference providers approved by digital Baseline B."""
    enable_cuda_dlls()
    root = models_root.resolve()
    asr = FrozenRecoveryASRProvider(root)
    recovery = RecoveryDiarizer(
        root,
        gap=FROZEN_DIARIZATION_GAP_SECONDS,
        window=FROZEN_DIARIZATION_WINDOW_SECONDS,
    )
    selected = diarization_engine.strip().lower()
    if selected == "recovery":
        diarization = recovery
        diarization_readiness = (
            "RecoveryDiarizer:"
            f"gap{FROZEN_DIARIZATION_GAP_SECONDS}:"
            f"window{FROZEN_DIARIZATION_WINDOW_SECONDS}"
        )
        quality_readiness = "REQUIRED"
    elif selected == "community1":
        engine = Community1DiarizerAdapter.from_local_snapshot(
            python_executable=Path(community1_python or DEFAULT_COMMUNITY1_PYTHON),
            model_snapshot=Path(community1_model_snapshot or DEFAULT_COMMUNITY1_SNAPSHOT),
            cache_root=Path(community1_cache_root or DEFAULT_COMMUNITY1_CACHE_ROOT),
            device="cpu",
        )
        diarization = DiarizationProviderBridge(
            engine,
            embedding_provider=recovery.embedding_provider,
        )
        startup = engine.startup_metrics
        diarization_readiness = (
            f"Community1:{COMMUNITY1_REVISION}:offline:"
            f"load_count{engine.model_load_count}:"
            f"startup{float(startup.get('model_load_seconds', 0.0)):.3f}s"
        )
        quality_readiness = "ECAPA_REIDENTIFICATION_SEPARATE"
    else:
        raise ValueError(f"unsupported diarization engine: {diarization_engine}")
    providers = WorkerProviders(
        asr=asr,
        diarization=diarization,
        embedding=recovery.embedding_provider,
        reasoning=None,
    )
    readiness = {
        "profile": "FROZEN_GOOD_BASELINE",
        "asr": f"{FROZEN_ASR_MODEL}:{FROZEN_ASR_VARIANT}:beam{FROZEN_ASR_BEAM}",
        "asr_runtime": "CUDA_FP16",
        "diarization": diarization_readiness,
        "diarization_engine": selected,
        "observation_quality": quality_readiness,
        "reasoning": "DISABLED_ON_REMOTE_WORKER",
    }
    return providers, readiness


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    token = os.environ.get("SAFE_FIELD_RAZER_WORKER_TOKEN")
    providers, readiness = compose_frozen_worker_providers(
        args.models_root,
        diarization_engine=args.diarization_engine,
        community1_python=args.community1_python,
        community1_cache_root=args.community1_cache_root,
        community1_model_snapshot=args.community1_model_snapshot,
    )
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
        close = getattr(providers.diarization, "close", None)
        if callable(close):
            close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
