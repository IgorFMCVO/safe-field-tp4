# UART TX pin documentary verification

Selected FPGA signal: `uart_tx` on Tang Nano 4K package pin 39.

The official Sipeed Tang Nano 4K revision 3603 schematic identifies package
pin 39 as `IOT26A` in Bank 1. `VCCO1` is tied to `DCDC2_3V3`, so the applicable
single-ended standard is LVCMOS33. The same sheet routes pin 39 to `PIXDATA8`
on expansion/camera connector P7 position 6. It is not a JTAG, configuration,
MSPI flash, HDMI, LED, key, oscillator, I2S or GPIO17 net.

The only board-level shared function is DVP `PIXDATA8`. The camera connector is
physically disconnected for this phase; therefore the FPGA may safely drive
the net as UART TX without bus contention. This condition is mandatory: do not
reconnect the camera while this bitstream is loaded.

Frozen TP4 mappings remain package pins 45/40/41/42/43/10. The new constraint
adds only pin 39 as a 3.3 V output.

Official source:
<https://dl.sipeed.com/fileList/TANG/Nano%204K/HDK/02_Schematic/Tang_Nano_4K_3603_Schematic_.pdf>

Planned receiver: Raspberry Pi GPIO15/RXD0, physical header pin 10. Both ends
use 3.3 V logic. A shared ground is required; Raspberry physical pin 9 and Tang
GND are already the validated common ground, but continuity remains an operator
responsibility before loading this bridge build.
