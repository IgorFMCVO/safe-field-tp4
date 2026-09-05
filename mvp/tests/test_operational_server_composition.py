from __future__ import annotations

from io import StringIO
from pathlib import Path
import ssl
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from mvp import razer_worker_service
from raspberry.safe_field_core import safe_field_operational_server as launcher


class OperationalServerCompositionTests(unittest.TestCase):
    def args(self, *extra: str):
        return launcher.build_argument_parser({}).parse_args(
            ["--diao-index", str(Path("ignored-local-diao-index")), *extra]
        )

    def test_default_composition_remains_entirely_local(self):
        args = self.args()
        local = SimpleNamespace(
            asr=object(),
            diarization=object(),
            embedding=object(),
            readiness={"asr": "READY", "diarization": "BLOCKED", "embedding": "READY"},
        )
        knowledge = object()
        reasoning = object()
        with (
            patch.object(launcher, "build_local_ai_provider_bundle", return_value=local) as build,
            patch.object(launcher, "MVPAsyncDIAOKnowledgeProvider", return_value=knowledge),
            patch.object(launcher, "LocalGroundedReasoningProvider", return_value=reasoning),
            patch.object(launcher, "RazerWorkerClient") as remote_client,
        ):
            providers, readiness = launcher.compose_pipeline_providers(args, {})

        build.assert_called_once_with(device="cpu", asr_compute_type="int8")
        remote_client.assert_not_called()
        self.assertIs(providers.asr, local.asr)
        self.assertIs(providers.diarization, local.diarization)
        self.assertIs(providers.embedding, local.embedding)
        self.assertIs(providers.reasoning, reasoning)
        self.assertIs(providers.knowledge, knowledge)
        self.assertEqual(readiness["mode"], "LOCAL")
        self.assertEqual(readiness["knowledge"], "LOCAL_DIAO")

    def test_razer_worker_defaults_to_the_validated_cpu_runtime(self):
        args = razer_worker_service.parser().parse_args([])

        self.assertEqual(args.device, "cpu")

    def test_remote_composition_uses_env_secrets_and_keeps_diao_on_pi(self):
        args = self.args("--ai-mode", "razer", "--razer-timeout-seconds", "12")
        environment = {
            "SAFE_FIELD_RAZER_WORKER_URL": "https://192.168.10.20:8766",
            "SAFE_FIELD_RAZER_WORKER_TOKEN": "fixture-worker-bearer",
            "SAFE_FIELD_RAZER_SCOPE_SECRET": "fixture-pi-only-scope-secret",
        }
        knowledge = object()
        client = object()
        remote_bundle = object()
        with (
            patch.object(launcher, "build_local_ai_provider_bundle") as local_builder,
            patch.object(launcher, "MVPAsyncDIAOKnowledgeProvider", return_value=knowledge),
            patch.object(launcher, "RazerWorkerClient", return_value=client) as client_factory,
            patch.object(
                launcher, "remote_pipeline_providers", return_value=remote_bundle
            ) as remote_factory,
        ):
            providers, readiness = launcher.compose_pipeline_providers(args, environment)

        local_builder.assert_not_called()
        client_factory.assert_called_once_with(
            environment["SAFE_FIELD_RAZER_WORKER_URL"],
            bearer_token=environment["SAFE_FIELD_RAZER_WORKER_TOKEN"],
            scope_secret=environment["SAFE_FIELD_RAZER_SCOPE_SECRET"],
            timeout_seconds=12.0,
            allow_insecure_private_http=False,
        )
        remote_factory.assert_called_once_with(client, knowledge=knowledge)
        self.assertIs(providers, remote_bundle)
        serialized = repr(readiness)
        for secret in environment.values():
            self.assertNotIn(secret, serialized)
        self.assertEqual(readiness["mode"], "RAZER_REMOTE")
        self.assertEqual(readiness["knowledge"], "LOCAL_DIAO")

    def test_remote_mode_can_be_selected_by_env_but_requires_scope_secret(self):
        parser = launcher.build_argument_parser({"SAFE_FIELD_AI_MODE": "razer"})
        args = parser.parse_args([])
        self.assertEqual(args.ai_mode, "razer")
        environment = {
            "SAFE_FIELD_RAZER_WORKER_URL": "http://127.0.0.1:8766",
            "SAFE_FIELD_RAZER_WORKER_TOKEN": "fixture-token-not-reported",
        }
        with patch.object(launcher, "MVPAsyncDIAOKnowledgeProvider", return_value=object()):
            with self.assertRaises(launcher.ConfigurationError) as raised:
                launcher.compose_pipeline_providers(args, environment)
        message = str(raised.exception)
        self.assertIn("SAFE_FIELD_RAZER_SCOPE_SECRET", message)
        self.assertNotIn(environment["SAFE_FIELD_RAZER_WORKER_TOKEN"], message)

    def test_custom_env_names_and_insecure_opt_in_are_forwarded_without_values_in_readiness(self):
        args = self.args(
            "--ai-mode", "razer",
            "--razer-worker-url-env", "CUSTOM_URL",
            "--razer-worker-token-env", "CUSTOM_TOKEN",
            "--razer-scope-secret-env", "CUSTOM_SCOPE",
            "--allow-insecure-razer-http",
        )
        environment = {
            "CUSTOM_URL": "http://192.168.1.44:8766",
            "CUSTOM_TOKEN": "custom-fixture-token",
            "CUSTOM_SCOPE": "custom-fixture-scope-secret",
        }
        client = object()
        with (
            patch.object(launcher, "MVPAsyncDIAOKnowledgeProvider", return_value=object()),
            patch.object(launcher, "RazerWorkerClient", return_value=client) as factory,
            patch.object(launcher, "remote_pipeline_providers", return_value=Mock()),
        ):
            _, readiness = launcher.compose_pipeline_providers(args, environment)
        self.assertTrue(factory.call_args.kwargs["allow_insecure_private_http"])
        rendered = repr(readiness)
        self.assertNotIn(environment["CUSTOM_TOKEN"], rendered)
        self.assertNotIn(environment["CUSTOM_SCOPE"], rendered)

    def test_tls_paths_can_come_from_environment_or_cli(self):
        environment = {
            launcher.TLS_CERT_ENV: "  environment-cert.pem  ",
            launcher.TLS_KEY_ENV: "  environment-key.pem  ",
        }

        from_environment = launcher.build_argument_parser(environment).parse_args([])
        from_cli = launcher.build_argument_parser(environment).parse_args(
            ["--tls-cert", "cli-cert.pem", "--tls-key", "cli-key.pem"]
        )

        self.assertEqual(from_environment.tls_cert, Path("environment-cert.pem"))
        self.assertEqual(from_environment.tls_key, Path("environment-key.pem"))
        self.assertEqual(from_cli.tls_cert, Path("cli-cert.pem"))
        self.assertEqual(from_cli.tls_key, Path("cli-key.pem"))

    def test_tls_context_requires_a_complete_pair(self):
        for certfile, keyfile in ((Path("cert.pem"), None), (None, Path("key.pem"))):
            with self.subTest(certfile=certfile, keyfile=keyfile):
                with self.assertRaises(launcher.ConfigurationError) as raised:
                    launcher._build_server_tls_context(certfile, keyfile)
                self.assertIn("configured together", str(raised.exception))

    def test_tls_context_uses_server_protocol_and_tls_1_2_minimum(self):
        context = Mock()
        with patch.object(launcher.ssl, "SSLContext", return_value=context) as factory:
            result = launcher._build_server_tls_context(Path("cert.pem"), Path("key.pem"))

        self.assertIs(result, context)
        factory.assert_called_once_with(ssl.PROTOCOL_TLS_SERVER)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        context.load_cert_chain.assert_called_once_with(
            certfile="cert.pem",
            keyfile="key.pem",
        )

    def test_tls_context_maps_certificate_load_failure_to_safe_configuration_error(self):
        with self.assertRaises(launcher.ConfigurationError) as raised:
            launcher._build_server_tls_context(
                Path("__missing_safe_field_tls_cert__.pem"),
                Path("__missing_safe_field_tls_key__.pem"),
            )

        self.assertIn("unable to load TLS certificate/key", str(raised.exception))

    def test_non_loopback_bearer_fails_closed_without_tls(self):
        environment = {"SAFE_FIELD_OPERATIONAL_API_TOKEN": "fixture-api-token"}
        stderr = StringIO()
        with (
            patch("sys.stderr", stderr),
            patch.object(launcher, "compose_pipeline_providers") as compose,
            patch.object(launcher, "serve") as serve_http,
            self.assertRaises(SystemExit) as raised,
        ):
            launcher.main(["--host", "0.0.0.0"], environment)

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("requires HTTPS", stderr.getvalue())
        self.assertNotIn(environment["SAFE_FIELD_OPERATIONAL_API_TOKEN"], stderr.getvalue())
        compose.assert_not_called()
        serve_http.assert_not_called()

    def test_non_loopback_tls_does_not_replace_required_bearer(self):
        environment = {
            launcher.TLS_CERT_ENV: "server-cert.pem",
            launcher.TLS_KEY_ENV: "server-key.pem",
        }
        stderr = StringIO()
        with (
            patch("sys.stderr", stderr),
            patch.object(
                launcher,
                "_build_server_tls_context",
                return_value=Mock(),
            ),
            patch.object(launcher, "compose_pipeline_providers") as compose,
            patch.object(launcher, "_serve_tls") as serve_tls,
            self.assertRaises(SystemExit) as raised,
        ):
            launcher.main(["--host", "0.0.0.0"], environment)

        self.assertEqual(raised.exception.code, 2)
        self.assertIn("requires a bearer token", stderr.getvalue())
        compose.assert_not_called()
        serve_tls.assert_not_called()

    def test_loopback_bearer_keeps_plain_http_available(self):
        environment = {"SAFE_FIELD_OPERATIONAL_API_TOKEN": "fixture-api-token"}
        core = object()
        with (
            patch.object(
                launcher,
                "compose_pipeline_providers",
                return_value=(object(), {"mode": "LOCAL"}),
            ),
            patch.object(launcher, "OperationalIntelligenceCore", return_value=core),
            patch.object(launcher, "serve") as serve_http,
            patch.object(launcher, "_serve_tls") as serve_tls,
            patch("builtins.print") as print_mock,
        ):
            result = launcher.main(["--host", "127.0.0.1"], environment)

        self.assertEqual(result, 0)
        serve_http.assert_called_once()
        self.assertEqual(serve_http.call_args.args[1:], ("127.0.0.1", 8770))
        self.assertEqual(
            serve_http.call_args.kwargs["auth_token"],
            environment["SAFE_FIELD_OPERATIONAL_API_TOKEN"],
        )
        serve_tls.assert_not_called()
        self.assertIn(
            "SAFE_FIELD_OPERATIONAL_READY http://127.0.0.1:8770",
            [call.args[0] for call in print_mock.call_args_list],
        )

    def test_non_loopback_bearer_with_env_tls_uses_https_server(self):
        environment = {
            "SAFE_FIELD_OPERATIONAL_API_TOKEN": "fixture-api-token",
            launcher.TLS_CERT_ENV: "server-cert.pem",
            launcher.TLS_KEY_ENV: "server-key.pem",
        }
        tls_context = Mock()
        with (
            patch.object(
                launcher,
                "compose_pipeline_providers",
                return_value=(object(), {"mode": "LOCAL"}),
            ),
            patch.object(launcher, "OperationalIntelligenceCore", return_value=object()),
            patch.object(
                launcher,
                "_build_server_tls_context",
                return_value=tls_context,
            ) as build_tls,
            patch.object(launcher, "serve") as serve_http,
            patch.object(launcher, "_serve_tls") as serve_tls,
            patch("builtins.print") as print_mock,
        ):
            result = launcher.main(["--host", "0.0.0.0"], environment)

        self.assertEqual(result, 0)
        build_tls.assert_called_once_with(Path("server-cert.pem"), Path("server-key.pem"))
        serve_http.assert_not_called()
        serve_tls.assert_called_once()
        self.assertEqual(serve_tls.call_args.args[1:], ("0.0.0.0", 8770))
        self.assertIs(serve_tls.call_args.kwargs["tls_context"], tls_context)
        self.assertEqual(
            serve_tls.call_args.kwargs["auth_token"],
            environment["SAFE_FIELD_OPERATIONAL_API_TOKEN"],
        )
        self.assertIn(
            "SAFE_FIELD_OPERATIONAL_READY https://0.0.0.0:8770",
            [call.args[0] for call in print_mock.call_args_list],
        )

    def test_tls_server_wraps_socket_before_serving_and_closes(self):
        raw_socket = object()
        wrapped_socket = object()
        server = Mock()
        server.socket = raw_socket
        tls_context = Mock()
        tls_context.wrap_socket.return_value = wrapped_socket
        handler = object()
        with (
            patch.object(launcher, "make_handler", return_value=handler) as make_handler,
            patch.object(
                launcher,
                "ThreadingHTTPServer",
                return_value=server,
            ) as server_factory,
        ):
            launcher._serve_tls(
                object(),
                "0.0.0.0",
                8770,
                auth_token="fixture-api-token",
                tls_context=tls_context,
            )

        make_handler.assert_called_once()
        self.assertEqual(make_handler.call_args.kwargs["auth_token"], "fixture-api-token")
        server_factory.assert_called_once_with(("0.0.0.0", 8770), handler)
        tls_context.wrap_socket.assert_called_once_with(raw_socket, server_side=True)
        self.assertIs(server.socket, wrapped_socket)
        server.serve_forever.assert_called_once_with()
        server.server_close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main(verbosity=2)
