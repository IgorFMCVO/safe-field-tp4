"""Optional live PCM source contract for the operational core.

The core owns occurrence lifecycle while a source owns the transport.  Keeping
the boundary this small lets tests inject a deterministic source and keeps the
approved TP4 UART bridge independent from the additive PCM build.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol


PCMSink = Callable[[bytes], None]


class PCMSource(Protocol):
    """Lifecycle contract implemented by physical and test PCM sources."""

    def start(self, sink: PCMSink) -> dict[str, Any]:
        """Open the source and begin delivering complete PCM16 frames."""

    def stop(self) -> dict[str, Any]:
        """Stop delivery, close the transport and return final counters."""

    def status(self) -> dict[str, Any]:
        """Return a thread-safe snapshot without secrets or mutable objects.

        Threaded sources report ``reader_alive`` and ``quiescent`` so the Core
        never claims capture stopped while an in-flight delivery is possible.
        """
