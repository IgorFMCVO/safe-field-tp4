module gw_gao(
    internal_reset_n,
    i2s_sck,
    i2s_ws,
    i2s_sd,
    capture_strobe,
    \capture_bit_index[5] ,
    \capture_bit_index[4] ,
    \capture_bit_index[3] ,
    \capture_bit_index[2] ,
    \capture_bit_index[1] ,
    \capture_bit_index[0] ,
    sample_valid,
    sample_channel,
    i2s_frame_error,
    sys_clk,
    \sample_data[23] ,
    \sample_data[22] ,
    \sample_data[21] ,
    \sample_data[20] ,
    \sample_data[19] ,
    \sample_data[18] ,
    \sample_data[17] ,
    \sample_data[16] ,
    \sample_data[15] ,
    \sample_data[14] ,
    \sample_data[13] ,
    \sample_data[12] ,
    \sample_data[11] ,
    \sample_data[10] ,
    \sample_data[9] ,
    \sample_data[8] ,
    \sample_data[7] ,
    \sample_data[6] ,
    \sample_data[5] ,
    \sample_data[4] ,
    \sample_data[3] ,
    \sample_data[2] ,
    \sample_data[1] ,
    \sample_data[0] ,
    sample_valid_toggle,
    i2s_frame_error_latched,
    \left_sample_count[15] ,
    \left_sample_count[14] ,
    \left_sample_count[13] ,
    \left_sample_count[12] ,
    \left_sample_count[11] ,
    \left_sample_count[10] ,
    \left_sample_count[9] ,
    \left_sample_count[8] ,
    \left_sample_count[7] ,
    \left_sample_count[6] ,
    \left_sample_count[5] ,
    \left_sample_count[4] ,
    \left_sample_count[3] ,
    \left_sample_count[2] ,
    \left_sample_count[1] ,
    \left_sample_count[0] ,
    \zero_left_count[15] ,
    \zero_left_count[14] ,
    \zero_left_count[13] ,
    \zero_left_count[12] ,
    \zero_left_count[11] ,
    \zero_left_count[10] ,
    \zero_left_count[9] ,
    \zero_left_count[8] ,
    \zero_left_count[7] ,
    \zero_left_count[6] ,
    \zero_left_count[5] ,
    \zero_left_count[4] ,
    \zero_left_count[3] ,
    \zero_left_count[2] ,
    \zero_left_count[1] ,
    \zero_left_count[0] ,
    \nonzero_left_count[15] ,
    \nonzero_left_count[14] ,
    \nonzero_left_count[13] ,
    \nonzero_left_count[12] ,
    \nonzero_left_count[11] ,
    \nonzero_left_count[10] ,
    \nonzero_left_count[9] ,
    \nonzero_left_count[8] ,
    \nonzero_left_count[7] ,
    \nonzero_left_count[6] ,
    \nonzero_left_count[5] ,
    \nonzero_left_count[4] ,
    \nonzero_left_count[3] ,
    \nonzero_left_count[2] ,
    \nonzero_left_count[1] ,
    \nonzero_left_count[0] ,
    \frame_error_count[15] ,
    \frame_error_count[14] ,
    \frame_error_count[13] ,
    \frame_error_count[12] ,
    \frame_error_count[11] ,
    \frame_error_count[10] ,
    \frame_error_count[9] ,
    \frame_error_count[8] ,
    \frame_error_count[7] ,
    \frame_error_count[6] ,
    \frame_error_count[5] ,
    \frame_error_count[4] ,
    \frame_error_count[3] ,
    \frame_error_count[2] ,
    \frame_error_count[1] ,
    \frame_error_count[0] ,
    \sd_transition_count[15] ,
    \sd_transition_count[14] ,
    \sd_transition_count[13] ,
    \sd_transition_count[12] ,
    \sd_transition_count[11] ,
    \sd_transition_count[10] ,
    \sd_transition_count[9] ,
    \sd_transition_count[8] ,
    \sd_transition_count[7] ,
    \sd_transition_count[6] ,
    \sd_transition_count[5] ,
    \sd_transition_count[4] ,
    \sd_transition_count[3] ,
    \sd_transition_count[2] ,
    \sd_transition_count[1] ,
    \sd_transition_count[0] ,
    tms_pad_i,
    tck_pad_i,
    tdi_pad_i,
    tdo_pad_o
);

input internal_reset_n;
input i2s_sck;
input i2s_ws;
input i2s_sd;
input capture_strobe;
input \capture_bit_index[5] ;
input \capture_bit_index[4] ;
input \capture_bit_index[3] ;
input \capture_bit_index[2] ;
input \capture_bit_index[1] ;
input \capture_bit_index[0] ;
input sample_valid;
input sample_channel;
input i2s_frame_error;
input sys_clk;
input \sample_data[23] ;
input \sample_data[22] ;
input \sample_data[21] ;
input \sample_data[20] ;
input \sample_data[19] ;
input \sample_data[18] ;
input \sample_data[17] ;
input \sample_data[16] ;
input \sample_data[15] ;
input \sample_data[14] ;
input \sample_data[13] ;
input \sample_data[12] ;
input \sample_data[11] ;
input \sample_data[10] ;
input \sample_data[9] ;
input \sample_data[8] ;
input \sample_data[7] ;
input \sample_data[6] ;
input \sample_data[5] ;
input \sample_data[4] ;
input \sample_data[3] ;
input \sample_data[2] ;
input \sample_data[1] ;
input \sample_data[0] ;
input sample_valid_toggle;
input i2s_frame_error_latched;
input \left_sample_count[15] ;
input \left_sample_count[14] ;
input \left_sample_count[13] ;
input \left_sample_count[12] ;
input \left_sample_count[11] ;
input \left_sample_count[10] ;
input \left_sample_count[9] ;
input \left_sample_count[8] ;
input \left_sample_count[7] ;
input \left_sample_count[6] ;
input \left_sample_count[5] ;
input \left_sample_count[4] ;
input \left_sample_count[3] ;
input \left_sample_count[2] ;
input \left_sample_count[1] ;
input \left_sample_count[0] ;
input \zero_left_count[15] ;
input \zero_left_count[14] ;
input \zero_left_count[13] ;
input \zero_left_count[12] ;
input \zero_left_count[11] ;
input \zero_left_count[10] ;
input \zero_left_count[9] ;
input \zero_left_count[8] ;
input \zero_left_count[7] ;
input \zero_left_count[6] ;
input \zero_left_count[5] ;
input \zero_left_count[4] ;
input \zero_left_count[3] ;
input \zero_left_count[2] ;
input \zero_left_count[1] ;
input \zero_left_count[0] ;
input \nonzero_left_count[15] ;
input \nonzero_left_count[14] ;
input \nonzero_left_count[13] ;
input \nonzero_left_count[12] ;
input \nonzero_left_count[11] ;
input \nonzero_left_count[10] ;
input \nonzero_left_count[9] ;
input \nonzero_left_count[8] ;
input \nonzero_left_count[7] ;
input \nonzero_left_count[6] ;
input \nonzero_left_count[5] ;
input \nonzero_left_count[4] ;
input \nonzero_left_count[3] ;
input \nonzero_left_count[2] ;
input \nonzero_left_count[1] ;
input \nonzero_left_count[0] ;
input \frame_error_count[15] ;
input \frame_error_count[14] ;
input \frame_error_count[13] ;
input \frame_error_count[12] ;
input \frame_error_count[11] ;
input \frame_error_count[10] ;
input \frame_error_count[9] ;
input \frame_error_count[8] ;
input \frame_error_count[7] ;
input \frame_error_count[6] ;
input \frame_error_count[5] ;
input \frame_error_count[4] ;
input \frame_error_count[3] ;
input \frame_error_count[2] ;
input \frame_error_count[1] ;
input \frame_error_count[0] ;
input \sd_transition_count[15] ;
input \sd_transition_count[14] ;
input \sd_transition_count[13] ;
input \sd_transition_count[12] ;
input \sd_transition_count[11] ;
input \sd_transition_count[10] ;
input \sd_transition_count[9] ;
input \sd_transition_count[8] ;
input \sd_transition_count[7] ;
input \sd_transition_count[6] ;
input \sd_transition_count[5] ;
input \sd_transition_count[4] ;
input \sd_transition_count[3] ;
input \sd_transition_count[2] ;
input \sd_transition_count[1] ;
input \sd_transition_count[0] ;
input tms_pad_i;
input tck_pad_i;
input tdi_pad_i;
output tdo_pad_o;

wire internal_reset_n;
wire i2s_sck;
wire i2s_ws;
wire i2s_sd;
wire capture_strobe;
wire \capture_bit_index[5] ;
wire \capture_bit_index[4] ;
wire \capture_bit_index[3] ;
wire \capture_bit_index[2] ;
wire \capture_bit_index[1] ;
wire \capture_bit_index[0] ;
wire sample_valid;
wire sample_channel;
wire i2s_frame_error;
wire sys_clk;
wire \sample_data[23] ;
wire \sample_data[22] ;
wire \sample_data[21] ;
wire \sample_data[20] ;
wire \sample_data[19] ;
wire \sample_data[18] ;
wire \sample_data[17] ;
wire \sample_data[16] ;
wire \sample_data[15] ;
wire \sample_data[14] ;
wire \sample_data[13] ;
wire \sample_data[12] ;
wire \sample_data[11] ;
wire \sample_data[10] ;
wire \sample_data[9] ;
wire \sample_data[8] ;
wire \sample_data[7] ;
wire \sample_data[6] ;
wire \sample_data[5] ;
wire \sample_data[4] ;
wire \sample_data[3] ;
wire \sample_data[2] ;
wire \sample_data[1] ;
wire \sample_data[0] ;
wire sample_valid_toggle;
wire i2s_frame_error_latched;
wire \left_sample_count[15] ;
wire \left_sample_count[14] ;
wire \left_sample_count[13] ;
wire \left_sample_count[12] ;
wire \left_sample_count[11] ;
wire \left_sample_count[10] ;
wire \left_sample_count[9] ;
wire \left_sample_count[8] ;
wire \left_sample_count[7] ;
wire \left_sample_count[6] ;
wire \left_sample_count[5] ;
wire \left_sample_count[4] ;
wire \left_sample_count[3] ;
wire \left_sample_count[2] ;
wire \left_sample_count[1] ;
wire \left_sample_count[0] ;
wire \zero_left_count[15] ;
wire \zero_left_count[14] ;
wire \zero_left_count[13] ;
wire \zero_left_count[12] ;
wire \zero_left_count[11] ;
wire \zero_left_count[10] ;
wire \zero_left_count[9] ;
wire \zero_left_count[8] ;
wire \zero_left_count[7] ;
wire \zero_left_count[6] ;
wire \zero_left_count[5] ;
wire \zero_left_count[4] ;
wire \zero_left_count[3] ;
wire \zero_left_count[2] ;
wire \zero_left_count[1] ;
wire \zero_left_count[0] ;
wire \nonzero_left_count[15] ;
wire \nonzero_left_count[14] ;
wire \nonzero_left_count[13] ;
wire \nonzero_left_count[12] ;
wire \nonzero_left_count[11] ;
wire \nonzero_left_count[10] ;
wire \nonzero_left_count[9] ;
wire \nonzero_left_count[8] ;
wire \nonzero_left_count[7] ;
wire \nonzero_left_count[6] ;
wire \nonzero_left_count[5] ;
wire \nonzero_left_count[4] ;
wire \nonzero_left_count[3] ;
wire \nonzero_left_count[2] ;
wire \nonzero_left_count[1] ;
wire \nonzero_left_count[0] ;
wire \frame_error_count[15] ;
wire \frame_error_count[14] ;
wire \frame_error_count[13] ;
wire \frame_error_count[12] ;
wire \frame_error_count[11] ;
wire \frame_error_count[10] ;
wire \frame_error_count[9] ;
wire \frame_error_count[8] ;
wire \frame_error_count[7] ;
wire \frame_error_count[6] ;
wire \frame_error_count[5] ;
wire \frame_error_count[4] ;
wire \frame_error_count[3] ;
wire \frame_error_count[2] ;
wire \frame_error_count[1] ;
wire \frame_error_count[0] ;
wire \sd_transition_count[15] ;
wire \sd_transition_count[14] ;
wire \sd_transition_count[13] ;
wire \sd_transition_count[12] ;
wire \sd_transition_count[11] ;
wire \sd_transition_count[10] ;
wire \sd_transition_count[9] ;
wire \sd_transition_count[8] ;
wire \sd_transition_count[7] ;
wire \sd_transition_count[6] ;
wire \sd_transition_count[5] ;
wire \sd_transition_count[4] ;
wire \sd_transition_count[3] ;
wire \sd_transition_count[2] ;
wire \sd_transition_count[1] ;
wire \sd_transition_count[0] ;
wire tms_pad_i;
wire tck_pad_i;
wire tdi_pad_i;
wire tdo_pad_o;
wire tms_i_c;
wire tck_i_c;
wire tdi_i_c;
wire tdo_o_c;
wire [9:0] control0;
wire [9:0] control1;
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
    .control1(control1[9:0]),
    .enable_i(enable_er1),
    .shift_dr_capture_dr_i(shift_dr_capture_dr),
    .update_dr_i(update_dr)
);

ao_top_0  u_la0_top(
    .control(control0[9:0]),
    .trig0_i(sample_valid),
    .data_i({internal_reset_n,i2s_sck,i2s_ws,i2s_sd,capture_strobe,\capture_bit_index[5] ,\capture_bit_index[4] ,\capture_bit_index[3] ,\capture_bit_index[2] ,\capture_bit_index[1] ,\capture_bit_index[0] ,sample_valid,sample_channel,i2s_frame_error}),
    .clk_i(sys_clk)
);

ao_top_1  u_la1_top(
    .control(control1[9:0]),
    .trig0_i(sample_valid_toggle),
    .data_i({\sample_data[23] ,\sample_data[22] ,\sample_data[21] ,\sample_data[20] ,\sample_data[19] ,\sample_data[18] ,\sample_data[17] ,\sample_data[16] ,\sample_data[15] ,\sample_data[14] ,\sample_data[13] ,\sample_data[12] ,\sample_data[11] ,\sample_data[10] ,\sample_data[9] ,\sample_data[8] ,\sample_data[7] ,\sample_data[6] ,\sample_data[5] ,\sample_data[4] ,\sample_data[3] ,\sample_data[2] ,\sample_data[1] ,\sample_data[0] ,sample_valid_toggle,sample_channel,i2s_frame_error_latched,\left_sample_count[15] ,\left_sample_count[14] ,\left_sample_count[13] ,\left_sample_count[12] ,\left_sample_count[11] ,\left_sample_count[10] ,\left_sample_count[9] ,\left_sample_count[8] ,\left_sample_count[7] ,\left_sample_count[6] ,\left_sample_count[5] ,\left_sample_count[4] ,\left_sample_count[3] ,\left_sample_count[2] ,\left_sample_count[1] ,\left_sample_count[0] ,\zero_left_count[15] ,\zero_left_count[14] ,\zero_left_count[13] ,\zero_left_count[12] ,\zero_left_count[11] ,\zero_left_count[10] ,\zero_left_count[9] ,\zero_left_count[8] ,\zero_left_count[7] ,\zero_left_count[6] ,\zero_left_count[5] ,\zero_left_count[4] ,\zero_left_count[3] ,\zero_left_count[2] ,\zero_left_count[1] ,\zero_left_count[0] ,\nonzero_left_count[15] ,\nonzero_left_count[14] ,\nonzero_left_count[13] ,\nonzero_left_count[12] ,\nonzero_left_count[11] ,\nonzero_left_count[10] ,\nonzero_left_count[9] ,\nonzero_left_count[8] ,\nonzero_left_count[7] ,\nonzero_left_count[6] ,\nonzero_left_count[5] ,\nonzero_left_count[4] ,\nonzero_left_count[3] ,\nonzero_left_count[2] ,\nonzero_left_count[1] ,\nonzero_left_count[0] ,\frame_error_count[15] ,\frame_error_count[14] ,\frame_error_count[13] ,\frame_error_count[12] ,\frame_error_count[11] ,\frame_error_count[10] ,\frame_error_count[9] ,\frame_error_count[8] ,\frame_error_count[7] ,\frame_error_count[6] ,\frame_error_count[5] ,\frame_error_count[4] ,\frame_error_count[3] ,\frame_error_count[2] ,\frame_error_count[1] ,\frame_error_count[0] ,\sd_transition_count[15] ,\sd_transition_count[14] ,\sd_transition_count[13] ,\sd_transition_count[12] ,\sd_transition_count[11] ,\sd_transition_count[10] ,\sd_transition_count[9] ,\sd_transition_count[8] ,\sd_transition_count[7] ,\sd_transition_count[6] ,\sd_transition_count[5] ,\sd_transition_count[4] ,\sd_transition_count[3] ,\sd_transition_count[2] ,\sd_transition_count[1] ,\sd_transition_count[0] }),
    .clk_i(i2s_ws)
);

endmodule
