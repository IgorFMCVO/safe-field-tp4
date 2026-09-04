module gw_gao(
    \calibrated_energy_q[13] ,
    \calibrated_energy_q[12] ,
    \calibrated_energy_q[11] ,
    \calibrated_energy_q[10] ,
    \calibrated_energy_q[9] ,
    \calibrated_energy_q[8] ,
    \calibrated_energy_q[7] ,
    \calibrated_energy_q[6] ,
    \calibrated_energy_q[5] ,
    \calibrated_energy_q[4] ,
    \calibrated_energy_q[3] ,
    \calibrated_energy_q[2] ,
    \calibrated_energy_q[1] ,
    \calibrated_energy_q[0] ,
    energy_overflow,
    pi_signal,
    frame_error_latched,
    sound_active,
    energy_capture_clock,
    tms_pad_i,
    tck_pad_i,
    tdi_pad_i,
    tdo_pad_o
);

input \calibrated_energy_q[13] ;
input \calibrated_energy_q[12] ;
input \calibrated_energy_q[11] ;
input \calibrated_energy_q[10] ;
input \calibrated_energy_q[9] ;
input \calibrated_energy_q[8] ;
input \calibrated_energy_q[7] ;
input \calibrated_energy_q[6] ;
input \calibrated_energy_q[5] ;
input \calibrated_energy_q[4] ;
input \calibrated_energy_q[3] ;
input \calibrated_energy_q[2] ;
input \calibrated_energy_q[1] ;
input \calibrated_energy_q[0] ;
input energy_overflow;
input pi_signal;
input frame_error_latched;
input sound_active;
input energy_capture_clock;
input tms_pad_i;
input tck_pad_i;
input tdi_pad_i;
output tdo_pad_o;

wire \calibrated_energy_q[13] ;
wire \calibrated_energy_q[12] ;
wire \calibrated_energy_q[11] ;
wire \calibrated_energy_q[10] ;
wire \calibrated_energy_q[9] ;
wire \calibrated_energy_q[8] ;
wire \calibrated_energy_q[7] ;
wire \calibrated_energy_q[6] ;
wire \calibrated_energy_q[5] ;
wire \calibrated_energy_q[4] ;
wire \calibrated_energy_q[3] ;
wire \calibrated_energy_q[2] ;
wire \calibrated_energy_q[1] ;
wire \calibrated_energy_q[0] ;
wire energy_overflow;
wire pi_signal;
wire frame_error_latched;
wire sound_active;
wire energy_capture_clock;
wire tms_pad_i;
wire tck_pad_i;
wire tdi_pad_i;
wire tdo_pad_o;
wire tms_i_c;
wire tck_i_c;
wire tdi_i_c;
wire tdo_o_c;
wire [9:0] control0;
wire gao_jtag_tck;
wire gao_jtag_reset;
wire run_test_idle_er1;
wire run_test_idle_er2;
wire shift_dr_capture_dr;
wire update_dr;
wire pause_dr;
wire enable_er1;
wire enable_er2;
wire gao_jtag_tdi;
wire tdo_er1;

IBUF tms_ibuf (
    .I(tms_pad_i),
    .O(tms_i_c)
);

IBUF tck_ibuf (
    .I(tck_pad_i),
    .O(tck_i_c)
);

IBUF tdi_ibuf (
    .I(tdi_pad_i),
    .O(tdi_i_c)
);

OBUF tdo_obuf (
    .I(tdo_o_c),
    .O(tdo_pad_o)
);

GW_JTAG  u_gw_jtag(
    .tms_pad_i(tms_i_c),
    .tck_pad_i(tck_i_c),
    .tdi_pad_i(tdi_i_c),
    .tdo_pad_o(tdo_o_c),
    .tck_o(gao_jtag_tck),
    .test_logic_reset_o(gao_jtag_reset),
    .run_test_idle_er1_o(run_test_idle_er1),
    .run_test_idle_er2_o(run_test_idle_er2),
    .shift_dr_capture_dr_o(shift_dr_capture_dr),
    .update_dr_o(update_dr),
    .pause_dr_o(pause_dr),
    .enable_er1_o(enable_er1),
    .enable_er2_o(enable_er2),
    .tdi_o(gao_jtag_tdi),
    .tdo_er1_i(tdo_er1),
    .tdo_er2_i(1'b0)
);

gw_con_top  u_icon_top(
    .tck_i(gao_jtag_tck),
    .tdi_i(gao_jtag_tdi),
    .tdo_o(tdo_er1),
    .rst_i(gao_jtag_reset),
    .control0(control0[9:0]),
    .enable_i(enable_er1),
    .shift_dr_capture_dr_i(shift_dr_capture_dr),
    .update_dr_i(update_dr)
);

ao_top_0  u_la0_top(
    .control(control0[9:0]),
    .trig0_i(pi_signal),
    .data_i({\calibrated_energy_q[13] ,\calibrated_energy_q[12] ,\calibrated_energy_q[11] ,\calibrated_energy_q[10] ,\calibrated_energy_q[9] ,\calibrated_energy_q[8] ,\calibrated_energy_q[7] ,\calibrated_energy_q[6] ,\calibrated_energy_q[5] ,\calibrated_energy_q[4] ,\calibrated_energy_q[3] ,\calibrated_energy_q[2] ,\calibrated_energy_q[1] ,\calibrated_energy_q[0] ,energy_overflow,pi_signal,frame_error_latched,sound_active}),
    .clk_i(energy_capture_clock)
);

endmodule
