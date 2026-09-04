# Raspberry UART configuration evidence

Date: 04/09/2026.

## Before

- `/boot/firmware/cmdline.txt` contained `console=serial0,115200`;
- no `/dev/serial0` node was present;
- GPIO14 and GPIO15 were inputs;
- serial getty units were disabled/inactive.

## Controlled change

Backups were created before editing:

- `/boot/firmware/config.txt.safe-field-pre-uart-20260904T1453`;
- `/boot/firmware/cmdline.txt.safe-field-pre-uart-20260904T1453`.

Commands executed on the Raspberry:

```bash
sudo raspi-config nonint do_serial_cons 1
sudo raspi-config nonint do_serial_hw 0
sudo reboot
```

The only functional changes were removal of `console=serial0,115200` from the
kernel command line and addition of `enable_uart=1`. The local `tty1` console
was preserved.

## After reboot

- `/dev/serial0 -> ttyS0`;
- `/dev/ttyS0` owner/group: `root:dialout`;
- service user is a member of `dialout`;
- GPIO14 = ALT5/TXD1;
- GPIO15 = ALT5/RXD1;
- serial getty remains inactive;
- `python3-serial` 3.5 installed from Debian packages.

No credentials are present in this file or in the captured logs.
