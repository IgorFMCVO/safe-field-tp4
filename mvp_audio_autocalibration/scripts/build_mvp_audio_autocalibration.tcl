set project_root [file normalize [file join [file dirname [info script]] ..]]
set repo_root [file normalize [file join $project_root ..]]
set build_dir [file join $repo_root build safe_field_mvp_audio_autocalibration]
file mkdir $build_dir
cd $build_dir

set constraint_file [file join $project_root constraints safe_field_mvp_audio_autocalibration.cst]
set f [open $constraint_file r]; set c [read $f]; close $f
foreach {signal pin} {sys_clk 45 pi_signal 40 i2s_sck 41 i2s_ws 42 i2s_sd 43 led 10 uart_tx 39 uart_rx 46} {
    if {![regexp [format {IO_LOC\s+"%s"\s+%s\s*;} $signal $pin] $c]} {
        error "SAFETY_GATE: expected $signal on pin $pin"
    }
}

set_device -name GW1NSR-4C GW1NSR-LV4CQN48PC6/I5
foreach file {
    rasp_to_tang.v i2s_clock_gen.v i2s_rx_24.v uart_tx_byte.v safe_field_telemetry_tx.v
} {
    add_file [file join $repo_root verilog_tp4 rtl frozen_baseline $file]
}
foreach file {
    safe_field_audio_energy_dsp.v safe_field_energy_bram.v uart_rx_byte.v safe_field_command_rx.v
} {
    add_file [file join $repo_root verilog_tp4 rtl $file]
}
foreach file {audio_activity_k_of_n.v audio_energy_detector_runtime.v safe_field_mvp_audio_autocalibration.v} {
    add_file [file join $project_root rtl $file]
}
add_file $constraint_file
add_file [file join $project_root constraints safe_field_mvp_audio_autocalibration.sdc]
set_option -top_module safe_field_mvp_audio_autocalibration
set_option -verilog_std v2001
set_option -output_base_name safe_field_mvp_audio_autocalibration
set_option -print_all_synthesis_warning 1
set_option -show_all_warn 1
set_option -cst_warn_to_error 1
set_option -gen_text_timing_rpt 1
set_option -timing_driven 1
set_option -power_on_reset_monitor 1
run all
