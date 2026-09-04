`timescale 1ns/1ps

// Normal-rate SAFE-FIELD datapath plus a passive long-duration GAO sampler.
// Functional audio remains 24-bit at 42.1875 kframes/s. Only the GAO copy is
// decimated by 64 and shifted to 14 bits to retain 12.43 continuous seconds.
module safe_field_normal_acoustic_capture #(
    parameter integer POR_BITS = 8,
    parameter integer WINDOW_LOG2 = 8,
    parameter integer HALF_PERIOD_CLKS = 5,
    parameter integer DECIMATION_LOG2 = 6,
    parameter [23:0] THRESHOLD_ON  = 24'd50000,
    parameter [23:0] THRESHOLD_OFF = 24'd30000
) (
    input wire sys_clk,
    input wire pi_signal,
    input wire i2s_sd,
    output wire i2s_sck,
    output wire i2s_ws,
    output wire led
);
reg [POR_BITS-1:0] por_counter = {POR_BITS{1'b0}};
(* keep = "true" *) reg internal_reset_n = 1'b0;
always @(posedge sys_clk) begin
    if (por_counter != {POR_BITS{1'b1}}) begin
        por_counter <= por_counter + 1'b1;
        internal_reset_n <= 1'b0;
    end else internal_reset_n <= 1'b1;
end

wire capture_strobe;
wire [5:0] capture_bit_index;
(* keep = "true" *) wire signed [23:0] sample_data;
(* keep = "true" *) wire sample_valid;
(* keep = "true" *) wire sample_channel;
(* keep = "true" *) wire i2s_frame_error;
(* keep = "true" *) wire [23:0] magnitude;
(* keep = "true" *) wire frame_valid;
(* keep = "true" *) wire [23:0] energy;
(* keep = "true" *) wire sound_active;
wire gpio_led;

i2s_clock_gen #(.HALF_PERIOD_CLKS(HALF_PERIOD_CLKS), .SLOT_BITS(32)) clock_master (
    .clk(sys_clk), .reset_n(internal_reset_n), .i2s_sck(i2s_sck), .i2s_ws(i2s_ws),
    .capture_strobe(capture_strobe), .capture_bit_index(capture_bit_index)
);
i2s_rx_24 receiver (
    .clk(sys_clk), .reset_n(internal_reset_n), .capture_strobe(capture_strobe),
    .capture_bit_index(capture_bit_index), .channel_ws(i2s_ws), .serial_data(i2s_sd),
    .sample_data(sample_data), .sample_valid(sample_valid),
    .sample_channel(sample_channel), .frame_error(i2s_frame_error)
);
audio_energy_detector #(
    .WINDOW_LOG2(WINDOW_LOG2), .THRESHOLD_ON(THRESHOLD_ON),
    .THRESHOLD_OFF(THRESHOLD_OFF)
) detector (
    .clk(sys_clk), .reset_n(internal_reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(sample_channel),
    .magnitude(magnitude), .frame_valid(frame_valid), .energy(energy),
    .sound_active(sound_active)
);
rasp_to_tang gpio17_baseline (.pi_signal(pi_signal), .led(gpio_led));
assign led = gpio_led | sound_active;

(* keep = "true" *) reg signed [13:0] decimated_sample;
(* keep = "true" *) reg decimated_sample_clock;
(* keep = "true" *) reg frame_error_latched;
reg [DECIMATION_LOG2-1:0] decimation_count;
reg decimated_clock_pending;
always @(posedge sys_clk or negedge internal_reset_n) begin
    if (!internal_reset_n) begin
        decimated_sample <= 14'sd0;
        decimated_sample_clock <= 1'b0;
        frame_error_latched <= 1'b0;
        decimation_count <= {DECIMATION_LOG2{1'b0}};
        decimated_clock_pending <= 1'b0;
    end else begin
        decimated_sample_clock <= 1'b0;
        if (decimated_clock_pending) begin
            decimated_sample_clock <= 1'b1;
            decimated_clock_pending <= 1'b0;
        end
        if (i2s_frame_error) frame_error_latched <= 1'b1;
        if (sample_valid && !sample_channel) begin
            decimated_sample <= sample_data >>> 10;
            if (&decimation_count) begin
                decimation_count <= {DECIMATION_LOG2{1'b0}};
                decimated_clock_pending <= 1'b1;
            end else decimation_count <= decimation_count + 1'b1;
        end
    end
end
endmodule
