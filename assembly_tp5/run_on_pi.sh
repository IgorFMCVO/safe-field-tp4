#!/usr/bin/env bash
# Only for the TP5 v05 command firmware; NOT the running RAW24 service.
set -euo pipefail
if [[ "${1:-}" != "--tp5-command-firmware-confirmed" ]]; then
  echo "Refusing UART access: confirm the loaded firmware uses TP5 v05 at 115200." >&2
  echo "Usage: $0 --tp5-command-firmware-confirmed [/dev/serial0]" >&2
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
stty -F "$DEV" 115200 raw -echo -ixon -ixoff cs8 -parenb -cstopb min 0 time 10
timeout 15s "$HERE/build/tp5_uart_demo" "$DEV"
