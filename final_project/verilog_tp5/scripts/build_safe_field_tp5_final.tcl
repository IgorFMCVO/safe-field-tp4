set component_root [file normalize [file join [file dirname [info script]] ..]]
set repo_root [file normalize [file join $component_root ..]]
set build_dir [file normalize [file join $component_root build safe_field_tp5_final]]

# This build is intentionally isolated from every frozen TP4/MVP build.
foreach protected_fragment {tp4-audio-inmp441 mvp_raw24_capture safe_field_tp4_validated} {
    if {[string first $protected_fragment $build_dir] >= 0} {
        error "SAFETY_GATE: TP5 final build cannot target protected path $build_dir"
    }
}
file mkdir $build_dir

set constraint_file [file join $component_root constraints safe_field_tp5.cst]
set f [open $constraint_file r]; set constraints [read $f]; close $f
foreach {signal pin} {sys_clk 45 pi_signal 40 i2s_sck 41 i2s_ws 42 i2s_sd 43 led 10 uart_tx 39 uart_rx 46} {
    if {![regexp [format {IO_LOC\s+"%s"\s+%s\s*;} $signal $pin] $constraints]} {
        error "SAFETY_GATE: expected $signal on package pin $pin"
    }
}
if {![regexp {IO_PORT\s+"i2s_sd"[^;]*PULL_MODE=DOWN} $constraints]} {
    error "SAFETY_GATE: i2s_sd must remain a pulled-down input"
}
if {![regexp {IO_PORT\s+"uart_rx"[^;]*PULL_MODE=UP} $constraints]} {
    error "SAFETY_GATE: uart_rx must remain a pulled-up input"
}

set top_file [file join $component_root rtl safe_field_tp5_top.v]
set f [open $top_file r]; set top_text [read $f]; close $f
if {![regexp {parameter\s+integer\s+UART_CLKS_PER_BIT=18} $top_text]} {
    error "SAFETY_GATE: the final TP5 UART must remain 1.5 Mbaud at 27 MHz"
}
if {![regexp {input\s+wire\s+i2s_sd} $top_text] || ![regexp {input\s+wire\s+uart_rx} $top_text]} {
    error "SAFETY_GATE: i2s_sd and uart_rx must both be top-level inputs"
}

cd $build_dir
set_device -name GW1NSR-4C GW1NSR-LV4CQN48PC6/I5
foreach rtl_file [lsort [glob [file join $component_root rtl *.v]]] {
    add_file $rtl_file
}
add_file $constraint_file
add_file [file join $component_root constraints safe_field_tp5.sdc]
set_option -top_module safe_field_tp5_top
set_option -verilog_std v2001
set_option -output_base_name safe_field_tp5_final
set_option -print_all_synthesis_warning 1
set_option -show_all_warn 1
set_option -cst_warn_to_error 1
set_option -gen_text_timing_rpt 1
set_option -timing_driven 1
set_option -power_on_reset_monitor 1
run all
