# SAFETY GATE: run only after i2s_sck/i2s_ws/i2s_sd have verified IO_LOC entries.
set project_root [file normalize [file join [file dirname [info script]] ..]]
set build_dir [file join $project_root build full]
file mkdir $build_dir
cd $build_dir

set constraint_file [file join $project_root src safe_field_tp4.cst]
set constraint_handle [open $constraint_file r]
set constraint_text [read $constraint_handle]
close $constraint_handle
set missing_signals {}
foreach required_signal {i2s_sck i2s_ws i2s_sd} {
    set required_pattern [format {IO_LOC\s+"%s"\s+[0-9]+\s*;} $required_signal]
    if {![regexp $required_pattern $constraint_text]} {
        lappend missing_signals $required_signal
    }
}
if {[llength $missing_signals] > 0} {
    set evidence_dir [file join $project_root evidence build]
    file mkdir $evidence_dir
    set safety_log [open [file join $evidence_dir full_build_blocked_missing_pinout.log] a]
    puts $safety_log "[clock format [clock seconds] -format {%Y-%m-%dT%H:%M:%S%z}] SAFETY_GATE BLOCKED"
    puts $safety_log "Missing verified IO_LOC: [join $missing_signals {, }]"
    puts $safety_log "Refused Place & Route and bitstream generation."
    close $safety_log
    error "SAFETY_GATE: missing verified IO_LOC for [join $missing_signals {, }]; refusing Place & Route and bitstream generation"
}

set_device -name GW1NSR-4C GW1NSR-LV4CQN48PC6/I5
add_file [file join $project_root src rasp_to_tang.v]
add_file [file join $project_root src i2s_clock_gen.v]
add_file [file join $project_root src i2s_rx_24.v]
add_file [file join $project_root src audio_energy_detector.v]
add_file [file join $project_root src safe_field_tp4.v]
add_file [file join $project_root src safe_field_tp4.cst]
add_file [file join $project_root src safe_field_tp4.sdc]
set_option -top_module safe_field_tp4
set_option -verilog_std v2001
set_option -output_base_name safe_field_tp4
set_option -print_all_synthesis_warning 1
set_option -show_all_warn 1
set_option -cst_warn_to_error 1
set_option -gen_text_timing_rpt 1
set_option -timing_driven 1
set_option -power_on_reset_monitor 1
run all
