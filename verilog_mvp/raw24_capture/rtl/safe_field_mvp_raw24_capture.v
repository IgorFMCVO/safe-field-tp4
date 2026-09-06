`timescale 1ns/1ps

// Additive simulation/build top for paired RAW24 and gain8 PCM16 capture.
// This diagnostic deliberately contains no energy detector or audio FSM:
// samples flow only through I2S acquisition, deterministic conversion and UART.
module safe_field_mvp_raw24_capture #(
    parameter integer POR_BITS = 8,
    parameter integer HALF_PERIOD_CLKS = 5,
    parameter integer UART_CLKS_PER_BIT = 18
) (
    input  wire sys_clk,
    input  wire pi_signal,
    input  wire i2s_sd,
    input  wire uart_rx,
    output wire i2s_sck,
    output wire i2s_ws,
    output wire led,
    output wire uart_tx
);
reg [POR_BITS-1:0] por_counter = {POR_BITS{1'b0}};
reg internal_reset_n = 1'b0;
always @(posedge sys_clk) begin
    if (por_counter != {POR_BITS{1'b1}}) begin
        por_counter <= por_counter + 1'b1;
        internal_reset_n <= 1'b0;
    end else begin
        internal_reset_n <= 1'b1;
    end
end

wire capture_strobe;
wire [5:0] capture_bit_index;
wire signed [23:0] sample_data;
wire sample_valid;
wire sample_channel;
wire i2s_frame_error;
wire transport_busy;
wire [31:0] source_sample_count;
wire [31:0] accepted_sample_count;
wire [31:0] dropped_sample_count;
wire transport_overrun;

i2s_clock_gen #(.HALF_PERIOD_CLKS(HALF_PERIOD_CLKS), .SLOT_BITS(32)) clock_master (
    .clk(sys_clk), .reset_n(internal_reset_n), .i2s_sck(i2s_sck),
    .i2s_ws(i2s_ws), .capture_strobe(capture_strobe),
    .capture_bit_index(capture_bit_index)
);

i2s_rx_24 receiver (
    .clk(sys_clk), .reset_n(internal_reset_n),
    .capture_strobe(capture_strobe), .capture_bit_index(capture_bit_index),
    .channel_ws(i2s_ws), .serial_data(i2s_sd), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(sample_channel),
    .frame_error(i2s_frame_error)
);

// Neutral indication only. GPIO17 remains observable without classifying audio
// or allowing any ENERGY/FSM state to affect the diagnostic sample stream.
assign led = pi_signal;

safe_field_raw24_packet_tx #(
    .UART_CLKS_PER_BIT(UART_CLKS_PER_BIT), .PCM_ARITH_SHIFT(5)
) raw24_transport (
    .clk(sys_clk), .reset_n(internal_reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(sample_channel),
    .frame_error(i2s_frame_error),
    .status_flags({4'd0, pi_signal, ~uart_rx}), .uart_tx(uart_tx),
    .busy(transport_busy), .source_sample_count(source_sample_count),
    .accepted_sample_count(accepted_sample_count),
    .dropped_sample_count(dropped_sample_count),
    .overrun_latched(transport_overrun)
);
endmodule
