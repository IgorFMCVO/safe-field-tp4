`timescale 1ns/1ps

// GATE A: low-rate, standards-compliant I2S acquisition with passive GAO
// observability.  The production I2S receiver is reused unchanged.
module debug6_low_rate_i2s #(
    parameter integer POR_BITS = 8,
    parameter integer HALF_PERIOD_CLKS = 27
) (
    input  wire sys_clk,
    input  wire pi_signal,
    input  wire i2s_sd,
    output wire i2s_sck,
    output wire i2s_ws,
    output wire led
);
reg [POR_BITS-1:0] por_counter = {POR_BITS{1'b0}};
(* keep = "true" *) reg internal_reset_n = 1'b0;

always @(posedge sys_clk) begin
    if (por_counter != {POR_BITS{1'b1}}) begin
        por_counter      <= por_counter + 1'b1;
        internal_reset_n <= 1'b0;
    end else begin
        internal_reset_n <= 1'b1;
    end
end

(* keep = "true" *) wire capture_strobe;
(* keep = "true" *) wire [5:0] capture_bit_index;
(* keep = "true" *) wire signed [23:0] sample_data;
(* keep = "true" *) wire sample_valid;
(* keep = "true" *) wire sample_channel;
(* keep = "true" *) wire i2s_frame_error;

i2s_clock_gen #(
    .HALF_PERIOD_CLKS(HALF_PERIOD_CLKS),
    .SLOT_BITS(32)
) clock_master (
    .clk(sys_clk),
    .reset_n(internal_reset_n),
    .i2s_sck(i2s_sck),
    .i2s_ws(i2s_ws),
    .capture_strobe(capture_strobe),
    .capture_bit_index(capture_bit_index)
);

i2s_rx_24 receiver (
    .clk(sys_clk),
    .reset_n(internal_reset_n),
    .capture_strobe(capture_strobe),
    .capture_bit_index(capture_bit_index),
    .channel_ws(i2s_ws),
    .serial_data(i2s_sd),
    .sample_data(sample_data),
    .sample_valid(sample_valid),
    .sample_channel(sample_channel),
    .frame_error(i2s_frame_error)
);

(* keep = "true" *) reg sample_valid_toggle;
(* keep = "true" *) reg i2s_frame_error_latched;
(* keep = "true" *) reg [15:0] left_sample_count;
(* keep = "true" *) reg [15:0] zero_left_count;
(* keep = "true" *) reg [15:0] nonzero_left_count;
(* keep = "true" *) reg [15:0] frame_error_count;
(* keep = "true" *) reg [15:0] sd_transition_count;
(* keep = "true" *) reg nonzero_seen;

reg sd_meta;
reg sd_sync;
reg sd_previous;

always @(posedge sys_clk or negedge internal_reset_n) begin
    if (!internal_reset_n) begin
        sample_valid_toggle     <= 1'b0;
        i2s_frame_error_latched <= 1'b0;
        left_sample_count       <= 16'd0;
        zero_left_count         <= 16'd0;
        nonzero_left_count      <= 16'd0;
        frame_error_count       <= 16'd0;
        sd_transition_count     <= 16'd0;
        nonzero_seen            <= 1'b0;
        sd_meta                 <= 1'b0;
        sd_sync                 <= 1'b0;
        sd_previous             <= 1'b0;
    end else begin
        sd_meta     <= i2s_sd;
        sd_sync     <= sd_meta;
        sd_previous <= sd_sync;

        if ((sd_sync != sd_previous) && !(&sd_transition_count))
            sd_transition_count <= sd_transition_count + 1'b1;

        if (i2s_frame_error) begin
            i2s_frame_error_latched <= 1'b1;
            if (!(&frame_error_count))
                frame_error_count <= frame_error_count + 1'b1;
        end

        if (sample_valid && !sample_channel) begin
            sample_valid_toggle <= ~sample_valid_toggle;
            if (!(&left_sample_count))
                left_sample_count <= left_sample_count + 1'b1;
            if (sample_data == 0) begin
                if (!(&zero_left_count))
                    zero_left_count <= zero_left_count + 1'b1;
            end else begin
                nonzero_seen <= 1'b1;
                if (!(&nonzero_left_count))
                    nonzero_left_count <= nonzero_left_count + 1'b1;
            end
        end
    end
end

// GPIO17 HIGH remains the independent validated override.  With GPIO17 LOW,
// the LED latches after the first nonzero LEFT sample for field visibility.
assign led = pi_signal | nonzero_seen;
endmodule
