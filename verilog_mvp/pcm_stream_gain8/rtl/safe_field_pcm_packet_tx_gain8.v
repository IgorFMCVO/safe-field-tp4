`timescale 1ns/1ps

// Additive gain8 front-end for the frozen, protocol-compatible PCM packet TX.
// All framing, sequence, counter, flags, CRC and UART timing remain implemented
// by safe_field_pcm_packet_tx without modification.
module safe_field_pcm_packet_tx_gain8 #(
    parameter integer UART_CLKS_PER_BIT = 18,
    parameter integer PCM_ARITH_SHIFT = 5
) (
    input  wire               clk,
    input  wire               reset_n,
    input  wire signed [23:0] sample_data,
    input  wire               sample_valid,
    input  wire               sample_channel,
    input  wire               frame_error,
    input  wire [5:0]         status_flags,
    output wire               uart_tx,
    output wire               busy,
    output wire [31:0]        accepted_sample_count,
    output wire [31:0]        dropped_sample_count,
    output wire               overrun_latched
);
wire signed [15:0] saturated_pcm16;
wire signed [23:0] packet_sample_data = {saturated_pcm16, 8'b0};

safe_field_pcm_s24_to_s16_sat #(.SHIFT(PCM_ARITH_SHIFT)) converter (
    .sample_in(sample_data),
    .sample_out(saturated_pcm16)
);

safe_field_pcm_packet_tx #(.UART_CLKS_PER_BIT(UART_CLKS_PER_BIT)) transport (
    .clk(clk),
    .reset_n(reset_n),
    .sample_data(packet_sample_data),
    .sample_valid(sample_valid),
    .sample_channel(sample_channel),
    .frame_error(frame_error),
    .status_flags(status_flags),
    .uart_tx(uart_tx),
    .busy(busy),
    .accepted_sample_count(accepted_sample_count),
    .dropped_sample_count(dropped_sample_count),
    .overrun_latched(overrun_latched)
);
endmodule

