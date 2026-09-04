set project_root [file normalize [file join [file dirname [info script]] ..]]
set debug_name debug5_external_wiring_levels
set build_dir [file join $project_root build $debug_name]
file mkdir $build_dir
cd $build_dir

# Refuse implementation unless every verified physical LOC is still exact.
set constraint_file [file join $project_root src safe_field_debug.cst]
set constraint_handle [open $constraint_file r]
set constraint_text [read $constraint_handle]
close $constraint_handle
foreach {required_signal required_pin} {
    sys_clk 45 pi_signal 40 i2s_sck 41 i2s_ws 42 i2s_sd 43 led 10
} {
    set required_pattern [format {IO_LOC\s+"%s"\s+%s\s*;} $required_signal $required_pin]
    if {![regexp $required_pattern $constraint_text]} {
        error "SAFETY_GATE: expected $required_signal on package pin $required_pin"
    }
}

set_device -name GW1NSR-4C GW1NSR-LV4CQN48PC6/I5
add_file [file join $project_root src debug5_external_wiring_levels.v]
add_file $constraint_file
add_file [file join $project_root src safe_field_debug.sdc]
set_option -top_module debug5_external_wiring_levels
set_option -verilog_std v2001
set_option -output_base_name $debug_name
set_option -print_all_synthesis_warning 1
set_option -show_all_warn 1
set_option -cst_warn_to_error 1
set_option -gen_text_timing_rpt 1
set_option -timing_driven 1
set_option -power_on_reset_monitor 1
run all
