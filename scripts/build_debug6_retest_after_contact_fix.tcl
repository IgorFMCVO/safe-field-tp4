set project_root [file normalize [file join [file dirname [info script]] ..]]
set build_dir [file join $project_root build debug6_retest_after_contact_fix]
file mkdir $build_dir
cd $build_dir

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
if {![regexp {IO_PORT\s+"i2s_sd"[^;]*PULL_MODE=DOWN} $constraint_text]} {
    error "SAFETY_GATE: expected passive i2s_sd input with PULL_MODE=DOWN"
}

# Preserve the original DEBUG6 build and create the deeper post-contact-fix GAO
# configuration inside this independent build directory.
set base_rao [file join $project_root src debug6_low_rate_i2s.rao]
set rao_handle [open $base_rao r]
set rao_text [read $rao_handle]
close $rao_handle
set rao_text [string map {
    {storage_depth="1024" window_num="1" capture_amount="1024" trigger_pos="128"}
    {storage_depth="4096" window_num="1" capture_amount="4096" trigger_pos="512"}
    {storage_depth="512" window_num="1" capture_amount="512" trigger_pos="64"}
    {storage_depth="1024" window_num="1" capture_amount="1024" trigger_pos="128"}
} $rao_text]
set rao_file [file join $build_dir debug6_retest_after_contact_fix.rao]
set rao_handle [open $rao_file w]
puts -nonewline $rao_handle $rao_text
close $rao_handle

set_device -name GW1NSR-4C GW1NSR-LV4CQN48PC6/I5
add_file [file join $project_root src rasp_to_tang.v]
add_file [file join $project_root src i2s_clock_gen.v]
add_file [file join $project_root src i2s_rx_24.v]
add_file [file join $project_root src debug6_low_rate_i2s.v]
add_file $constraint_file
add_file [file join $project_root src debug6_low_rate_i2s.sdc]
add_file $rao_file
set_option -top_module debug6_low_rate_i2s
set_option -verilog_std v2001
set_option -output_base_name debug6_retest_after_contact_fix
set_option -print_all_synthesis_warning 1
set_option -show_all_warn 1
set_option -cst_warn_to_error 1
set_option -gen_text_timing_rpt 1
set_option -timing_driven 1
set_option -power_on_reset_monitor 1
run all
