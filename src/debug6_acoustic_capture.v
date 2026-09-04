`timescale 1ns/1ps

// DEBUG6 acoustic-gate instrumentation. The clock generator and 24-bit I2S
// receiver are unchanged; only passive/visible decimation and trigger state are
// added so GAO can retain more than five seconds around a real voice event.
module debug6_acoustic_capture #(
    parameter integer POR_BITS = 8,
    parameter integer HALF_PERIOD_CLKS = 27,
    parameter [23:0] VOICE_TRIGGER_MAGNITUDE = 24'd32768
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

wire [23:0] current_magnitude = sample_data[23]
    ? (~sample_data + 1'b1) : sample_data;

(* keep = "true" *) reg signed [13:0] decimated_sample;
(* keep = "true" *) reg decimated_sample_clock;
(* keep = "true" *) reg voice_trigger_level;
(* keep = "true" *) reg frame_error_latched;
(* keep = "true" *) reg [31:0] left_sample_count;
reg [2:0] decimation_count;
reg decimated_clock_pending;
reg [5:0] voice_hold_samples;

always @(posedge sys_clk or negedge internal_reset_n) begin
    if (!internal_reset_n) begin
        decimated_sample        <= 16'sd0;
        decimated_sample_clock  <= 1'b0;
        voice_trigger_level     <= 1'b0;
        frame_error_latched     <= 1'b0;
        left_sample_count       <= 32'd0;
        decimation_count        <= 3'd0;
        decimated_clock_pending <= 1'b0;
        voice_hold_samples      <= 6'd0;
    end else begin
        decimated_sample_clock <= 1'b0;

        // The GAO sampling edge is delayed by one sys_clk so the compressed
        // sample and trigger are stable before the capture RAM clock edge.
        if (decimated_clock_pending) begin
            decimated_sample_clock  <= 1'b1;
            decimated_clock_pending <= 1'b0;
        end

        if (i2s_frame_error)
            frame_error_latched <= 1'b1;

        if (sample_valid && !sample_channel) begin
            left_sample_count <= left_sample_count + 1'b1;
            // The receiver remains 24-bit. Only the passive GAO copy is
            // compressed to 14 bits so an 8.39 s trace fits in GW1NSR-4C RAM.
            decimated_sample  <= sample_data >>> 10;

            if (decimation_count == 3'd7) begin
                decimation_count        <= 3'd0;
                decimated_clock_pending <= 1'b1;
            end else begin
                decimation_count <= decimation_count + 1'b1;
            end

            if (current_magnitude >= VOICE_TRIGGER_MAGNITUDE) begin
                voice_trigger_level <= 1'b1;
                voice_hold_samples  <= 6'd63;
            end else if (voice_hold_samples != 0) begin
                voice_trigger_level <= 1'b1;
                voice_hold_samples  <= voice_hold_samples - 1'b1;
            end else begin
                voice_trigger_level <= 1'b0;
            end
        end
    end
end

assign led = pi_signal | voice_trigger_level;
endmodule
