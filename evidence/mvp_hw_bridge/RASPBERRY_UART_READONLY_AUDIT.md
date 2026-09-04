# Raspberry UART read-only audit

Audit performed through the existing SSH session on 2026-09-04 at
13:34:55 -03. No Raspberry configuration was changed.

```text
15: ip pu | hi // GPIO15 = input
/dev/serial0: absent
/dev/ttyAMA0: absent
/dev/ttyS0: absent
serial-getty@ttyAMA0.service: disabled/inactive
serial-getty@serial0.service: disabled/inactive
```

Interpretation: GPIO15 is electrically an input with pull-up and no serial
getty is competing for it, but the OS UART device is not currently enabled.
After the boards are powered down, wired and rechecked, the next software phase
must enable the Raspberry UART and reboot before starting the receiver. That
configuration change was intentionally not made in this pre-wiring phase.
