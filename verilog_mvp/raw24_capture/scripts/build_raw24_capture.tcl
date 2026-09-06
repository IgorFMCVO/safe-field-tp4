set component_root [file normalize [file join [file dirname [info script]] ..]]
set repo_root [file normalize [file join $component_root .. ..]]
set build_dir [file normalize [file join $repo_root build mvp_raw24_capture]]
foreach protected_name {mvp_pcm_stream mvp_pcm_stream_gain8 safe_field_tp4 safe_field_tp4_official} {
    set protected_dir [file normalize [file join $repo_root build $protected_name]]
    if {$build_dir eq $protected_dir} {
        error "SAFETY_GATE: RAW24 diagnostic must not target protected build $protected_name"
    }
}
file mkdir $build_dir
cd $build_dir

set constraint_file [file join $component_root constraints safe_field_mvp_raw24_capture.cst]
set f [open $constraint_file r]; set c [read $f]; close $f
foreach {signal pin} {sys_clk 45 pi_signal 40 i2s_sck 41 i2s_ws 42 i2s_sd 43 led 10 uart_tx 39 uart_rx 46} {
    if {![regexp [format {IO_LOC\s+"%s"\s+%s\s*;} $signal $pin] $c]} {
        error "SAFETY_GATE: expected $signal on pin $pin"
    }
}
if {![regexp {IO_PORT\s+"i2s_sd"[^;]*PULL_MODE=DOWN} $c]} {
    error "SAFETY_GATE: i2s_sd must remain an input with validated pull-down"
}
if {![regexp {IO_PORT\s+"uart_rx"[^;]*PULL_MODE=UP} $c]} {
    error "SAFETY_GATE: uart_rx must remain a pulled-up input"
}

set_device -name GW1NSR-4C GW1NSR-LV4CQN48PC6/I5
foreach file {i2s_clock_gen.v i2s_rx_24.v uart_tx_byte.v} {
    add_file [file join $repo_root verilog_tp4 rtl frozen_baseline $file]
}
add_file [file join $repo_root verilog_mvp pcm_stream_gain8 rtl safe_field_pcm_s24_to_s16_sat.v]
add_file [file join $component_root rtl safe_field_raw24_packet_tx.v]
add_file [file join $component_root rtl safe_field_mvp_raw24_capture.v]
add_file $constraint_file
add_file [file join $component_root constraints safe_field_mvp_raw24_capture.sdc]
set_option -top_module safe_field_mvp_raw24_capture
set_option -verilog_std v2001
set_option -output_base_name safe_field_mvp_raw24_capture
set_option -print_all_synthesis_warning 1
set_option -show_all_warn 1
set_option -cst_warn_to_error 1
set_option -gen_text_timing_rpt 1
set_option -timing_driven 1
set_option -power_on_reset_monitor 1
run all
