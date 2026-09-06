#!/usr/bin/env python3
"""Launch the additive operational API without changing the approved TP4 bridge."""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
import ipaddress
import os
from pathlib import Path
import ssl
import sys
from typing import Mapping


REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))

from mvp.operational_intelligence.core import OperationalIntelligenceCore  # noqa: E402
from mvp.operational_intelligence.audio import PCMFormat, SegmenterConfig  # noqa: E402
from mvp.operational_intelligence.http_api import (  # noqa: E402
    OperationalApiService,
    make_handler,
    serve,
)
from mvp.operational_intelligence.grounded_reasoning import (  # noqa: E402
    LocalGroundedReasoningProvider,
)
from mvp.operational_intelligence.local_ai import build_local_ai_provider_bundle  # noqa: E402
from mvp.operational_intelligence.pipeline import PipelineProviders  # noqa: E402
from mvp.operational_intelligence.razer_worker_transport import (  # noqa: E402
    RazerWorkerClient,
    remote_pipeline_providers,
)
from mvp.operational_intelligence.structured_reasoning import (  # noqa: E402
    StructuredOccurrenceReasoner,
)
from operational_guidance.diao.mvp_adapter import MVPAsyncDIAOKnowledgeProvider  # noqa: E402
from raspberry_mvp.pcm_stream import SerialPCMSource  # noqa: E402


TLS_CERT_ENV = "SAFE_FIELD_OPERATIONAL_TLS_CERT"
TLS_KEY_ENV = "SAFE_FIELD_OPERATIONAL_TLS_KEY"
FROZEN_RECOVERY_SEGMENTATION = SegmenterConfig(speech_rms_threshold=150)


def _is_loopback_bind(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized == "localhost":
        return True
    try:
        return ipaddress.ip_address(normalized).is_loopback
    except ValueError:
        return False


class ConfigurationError(ValueError):
    """Safe startup failure containing environment names, never their values."""


def build_argument_parser(environ: Mapping[str, str] | None = None):
    environment = os.environ if environ is None else environ
    parser = argparse.ArgumentParser(description="SAFE-FIELD operational control plane")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument(
        "--tls-cert",
        type=Path,
        default=(
            Path(environment[TLS_CERT_ENV].strip())
            if environment.get(TLS_CERT_ENV, "").strip()
            else None
        ),
        help=f"PEM certificate chain; defaults to the path in {TLS_CERT_ENV}",
    )
    parser.add_argument(
        "--tls-key",
        type=Path,
        default=(
            Path(environment[TLS_KEY_ENV].strip())
            if environment.get(TLS_KEY_ENV, "").strip()
            else None
        ),
        help=f"PEM private key; defaults to the path in {TLS_KEY_ENV}",
    )
    parser.add_argument("--sessions-root", type=Path, default=Path("sessions"))
    parser.add_argument(
        "--pcm-port",
        help=(
            "optional additive FPGA PCM UART (for example /dev/serial0); "
            "opened only when WATCH START is accepted"
        ),
    )
    parser.add_argument(
        "--api-token-env",
        default="SAFE_FIELD_OPERATIONAL_API_TOKEN",
        help="environment variable containing the bearer token (the token is never logged)",
    )
    parser.add_argument(
        "--ai-device",
        choices=("cpu", "cuda"),
        default="cpu",
        help="local inference device; CPU is the validated default on this host",
    )
    parser.add_argument(
        "--asr-compute-type",
        default="int8",
        help="Faster-Whisper compute type (validated: int8 on CPU)",
    )
    parser.add_argument(
        "--ai-mode",
        choices=("local", "razer"),
        default=environment.get("SAFE_FIELD_AI_MODE", "local"),
        help="inference placement; local remains the fail-safe default",
    )
    parser.add_argument(
        "--razer-worker-url-env",
        default="SAFE_FIELD_RAZER_WORKER_URL",
        help="environment variable containing the private worker URL",
    )
    parser.add_argument(
        "--razer-worker-token-env",
        default="SAFE_FIELD_RAZER_WORKER_TOKEN",
        help="environment variable containing the worker bearer (never logged)",
    )
    parser.add_argument(
        "--razer-scope-secret-env",
        default="SAFE_FIELD_RAZER_SCOPE_SECRET",
        help="Pi-only environment variable for pseudonymous occurrence scopes",
    )
    parser.add_argument(
        "--razer-timeout-seconds",
        type=float,
        default=90.0,
        help="connect/read timeout for a remote inference request",
    )
    parser.add_argument(
        "--allow-insecure-razer-http",
        action="store_true",
        help="explicitly accept unencrypted worker traffic on a private LAN",
    )
    parser.add_argument(
        "--structured-reasoning-endpoint",
        default=environment.get(
            "SAFE_FIELD_STRUCTURED_REASONING_ENDPOINT",
            "http://127.0.0.1:18089",
        ),
        help=(
            "Pi-loopback LLM endpoint; for Razer execution expose it only through "
            "the authenticated SSH tunnel"
        ),
    )
    parser.add_argument(
        "--diao-index",
        type=Path,
        default=REPOSITORY / "knowledge" / "diao" / "index",
        help="local ignored DIAO index; never uploaded by this service",
    )
    return parser


def _build_server_tls_context(
    certfile: Path | None,
    keyfile: Path | None,
) -> ssl.SSLContext | None:
    if (certfile is None) != (keyfile is None):
        raise ConfigurationError(
            "TLS certificate and key must be configured together via "
            f"--tls-cert/--tls-key or {TLS_CERT_ENV}/{TLS_KEY_ENV}"
        )
    if certfile is None:
        return None

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    try:
        context.load_cert_chain(certfile=str(certfile), keyfile=str(keyfile))
    except OSError as exc:
        raise ConfigurationError(f"unable to load TLS certificate/key: {exc}") from exc
    return context


def _serve_tls(
    service: OperationalApiService,
    host: str,
    port: int,
    *,
    auth_token: str | None,
    tls_context: ssl.SSLContext,
) -> None:
    server = ThreadingHTTPServer(
        (host, port),
        make_handler(service, auth_token=auth_token),
    )
    try:
        server.socket = tls_context.wrap_socket(server.socket, server_side=True)
        server.serve_forever()
    finally:
        server.server_close()


def compose_pipeline_providers(
    args: argparse.Namespace,
    environ: Mapping[str, str] | None = None,
) -> tuple[PipelineProviders, dict[str, str]]:
    """Compose local or Razer inference while keeping DIAO on this Pi."""

    environment = os.environ if environ is None else environ
    knowledge = MVPAsyncDIAOKnowledgeProvider(index_dir=args.diao_index)
    if args.ai_mode == "local":
        local_ai = build_local_ai_provider_bundle(
            device=args.ai_device,
            asr_compute_type=args.asr_compute_type,
        )
        providers = PipelineProviders(
            asr=local_ai.asr,
            diarization=local_ai.diarization,
            embedding=local_ai.embedding,
            reasoning=LocalGroundedReasoningProvider(),
            knowledge=knowledge,
        )
        return providers, {**dict(local_ai.readiness), "mode": "LOCAL", "knowledge": "LOCAL_DIAO"}

    worker_url = environment.get(args.razer_worker_url_env, "").strip()
    worker_token = environment.get(args.razer_worker_token_env, "").strip() or None
    scope_secret = environment.get(args.razer_scope_secret_env, "")
    if not worker_url:
        raise ConfigurationError(
            f"razer mode requires worker URL in environment variable {args.razer_worker_url_env}"
        )
    if not scope_secret:
        raise ConfigurationError(
            "razer mode requires a Pi-only scope secret in environment variable "
            f"{args.razer_scope_secret_env}"
        )
    try:
        client = RazerWorkerClient(
            worker_url,
            bearer_token=worker_token,
            scope_secret=scope_secret,
            timeout_seconds=args.razer_timeout_seconds,
            allow_insecure_private_http=args.allow_insecure_razer_http,
        )
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"invalid Razer worker configuration: {exc}") from exc
    try:
        reasoning = StructuredOccurrenceReasoner(
            knowledge,
            endpoint=args.structured_reasoning_endpoint,
        )
        providers = remote_pipeline_providers(
            client,
            knowledge=knowledge,
            reasoning=reasoning,
        )
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(f"invalid structured reasoning configuration: {exc}") from exc
    readiness = {
        "mode": "RAZER_REMOTE",
        "transport": "CONFIGURED_NOT_PROBED",
        "asr": "REMOTE",
        "diarization": "REMOTE",
        "embedding": "REMOTE",
        "reasoning": "PI_LOCAL_STRUCTURED_VIA_LOOPBACK_LLM",
        "strict_support": "ENABLED",
        "observation_quality": "REMOTE_REQUIRED",
        "knowledge": "LOCAL_DIAO",
    }
    return providers, readiness


def main(
    argv: list[str] | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    environment = os.environ if environ is None else environ
    parser = build_argument_parser(environment)
    args = parser.parse_args(argv)
    api_token = environment.get(args.api_token_env, "").strip() or None
    try:
        tls_context = _build_server_tls_context(args.tls_cert, args.tls_key)
    except ConfigurationError as exc:
        parser.error(str(exc))
    if not _is_loopback_bind(args.host):
        if api_token is None:
            parser.error(
                "non-loopback bind requires a bearer token in environment variable "
                f"{args.api_token_env}"
            )
        if tls_context is None:
            parser.error(
                "non-loopback bearer authentication requires HTTPS via --tls-cert/--tls-key "
                f"or {TLS_CERT_ENV}/{TLS_KEY_ENV}"
            )
    try:
        providers, ai_readiness = compose_pipeline_providers(args, environment)
    except ConfigurationError as exc:
        parser.error(str(exc))
    pcm_source = SerialPCMSource(args.pcm_port) if args.pcm_port else None
    pcm_format = (
        PCMFormat(sample_rate=42_188, channels=1, sample_width=2)
        if pcm_source is not None
        else None
    )
    core = OperationalIntelligenceCore(
        args.sessions_root,
        providers=providers,
        pcm=pcm_format,
        segmentation=FROZEN_RECOVERY_SEGMENTATION if args.ai_mode == "razer" else None,
        pcm_source=pcm_source,
        physical_capture_only=pcm_source is not None,
    )
    scheme = "https" if tls_context is not None else "http"
    print(f"SAFE_FIELD_OPERATIONAL_READY {scheme}://{args.host}:{args.port}", flush=True)
    readiness_label = "LOCAL_AI_READINESS" if args.ai_mode == "local" else "AI_PROVIDER_READINESS"
    print(f"{readiness_label} {ai_readiness}", flush=True)
    print(
        "PCM_SOURCE_READY "
        + (
            f"UART_PCM16_V1 port={args.pcm_port} baud=1500000 rate=42188"
            if args.pcm_port
            else "DISABLED"
        ),
        flush=True,
    )
    service = OperationalApiService(core)
    if tls_context is None:
        serve(service, args.host, args.port, auth_token=api_token)
    else:
        _serve_tls(
            service,
            args.host,
            args.port,
            auth_token=api_token,
            tls_context=tls_context,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
