#!/usr/bin/env bash
# Physical TP5 coexistence client: 1.5 Mbaud, RAW24 may remain active and the
# Assembly client resynchronizes TP5 replies.  It is NOT compatible with the
# academic v05 image at 115200 unless that image is rebuilt with matching UART.
set -euo pipefail
if [[ "${1:-}" != "--tp5-physical-1m5-confirmed" ]]; then
  echo "Refusing UART access: confirm the loaded physical image supports TP5+RAW24 at 1500000." >&2
  echo "Usage: $0 --tp5-physical-1m5-confirmed [/dev/serial0]" >&2
  exit 2
fi
DEV="${2:-/dev/serial0}"
[[ -c "$DEV" ]] || { echo "Serial character device missing: $DEV" >&2; exit 2; }
command -v timeout >/dev/null || { echo "timeout is required" >&2; exit 2; }
if command -v fuser >/dev/null && fuser "$DEV" >/dev/null 2>&1; then
  echo "Serial is in use; do not run competing consumers." >&2
  exit 2
fi
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
[[ -x "$HERE/build/tp5_uart_demo" ]] || { echo "Build the AArch64 executable first." >&2; exit 2; }
OLD="$(stty -F "$DEV" -g)"
trap 'stty -F "$DEV" "$OLD" 2>/dev/null || true' EXIT
stty -F "$DEV" 1500000 raw -echo -ixon -ixoff cs8 -parenb -cstopb min 0 time 10
timeout 15s "$HERE/build/tp5_uart_demo" "$DEV"
