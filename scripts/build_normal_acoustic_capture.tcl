set project_root [file normalize [file join [file dirname [info script]] ..]]
set build_dir [file join $project_root build normal_acoustic_capture]
file mkdir $build_dir
cd $build_dir
set constraint_file [file join $project_root src safe_field_debug.cst]
set f [open $constraint_file r]; set c [read $f]; close $f
foreach {signal pin} {sys_clk 45 pi_signal 40 i2s_sck 41 i2s_ws 42 i2s_sd 43 led 10} {
    if {![regexp [format {IO_LOC\s+"%s"\s+%s\s*;} $signal $pin] $c]} {error "SAFETY_GATE: expected $signal on pin $pin"}
}
if {![regexp {IO_PORT\s+"i2s_sd"[^;]*PULL_MODE=DOWN} $c]} {error "SAFETY_GATE: i2s_sd must remain passive PULL_MODE=DOWN input"}
set_device -name GW1NSR-4C GW1NSR-LV4CQN48PC6/I5
foreach file {rasp_to_tang.v i2s_clock_gen.v i2s_rx_24.v audio_energy_detector.v safe_field_normal_acoustic_capture.v} {add_file [file join $project_root src $file]}
add_file $constraint_file
add_file [file join $project_root src safe_field_normal_acoustic_capture.sdc]
add_file [file join $project_root src safe_field_normal_acoustic_capture.rao]
set_option -top_module safe_field_normal_acoustic_capture
set_option -verilog_std v2001
set_option -output_base_name normal_acoustic_capture
set_option -print_all_synthesis_warning 1
set_option -show_all_warn 1
set_option -cst_warn_to_error 1
set_option -gen_text_timing_rpt 1
set_option -timing_driven 1
set_option -power_on_reset_monitor 1
run all
