set project_root [file normalize [file join [file dirname [info script]] ..]]
set build_dir [file join $project_root build synthesis]
file mkdir $build_dir
cd $build_dir

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
run syn
