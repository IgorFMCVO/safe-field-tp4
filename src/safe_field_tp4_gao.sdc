create_clock -name sys_clk -period 37.037 -waveform {0 18.5185} [get_ports {sys_clk}]

# The frame clock is generated synchronously: 5 sys_clk cycles per SCK half
# period, 64 SCK periods per stereo frame => divide by 640.
create_generated_clock -name i2s_ws_clk -source [get_ports {sys_clk}] -master_clock sys_clk -divide_by 640 [get_ports {i2s_ws}]

# GAO's JTAG transport is asynchronous to the user clocks. This follows the
# official FIFO_HS GAO example supplied with Gowin Designer. Programmer/capture
# commands below keep TCK at the matching 2.5 MHz (400 ns period).
create_clock -name tck_pad_i -period 400 -waveform {0 200} [get_ports {tck_pad_i}]
set_clock_groups -asynchronous -group [get_clocks {sys_clk i2s_ws_clk}] -group [get_clocks {tck_pad_i}]

report_timing -setup -from_clock [get_clocks {sys_clk}] -to_clock [get_clocks {sys_clk}] -max_paths 100 -max_common_paths 1
