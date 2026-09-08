#!/usr/bin/env bash
set -euo pipefail
DEV="${1:-/dev/serial0}"
if [[ "$DEV" != "/dev/serial0" ]]; then
  echo "TP5 uart_client.S currently opens /dev/serial0; pass no alternate device." >&2
  exit 2
fi
stty -F "$DEV" 115200 raw -echo -ixon -ixoff
./build/tp5_uart_demo
