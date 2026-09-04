`timescale 1ns/1ps

// Separate post-repair candidate.  The preserved safe_field_tp4 build remains
// unchanged; this top combines the validated I2S path with temporal filtering.
module safe_field_stable_audio #(
    parameter integer POR_BITS = 8,
    parameter integer WINDOW_LOG2 = 8,
    parameter integer HALF_PERIOD_CLKS = 5,
    parameter [23:0] THRESHOLD_ON  = 24'd12000,
    parameter [23:0] THRESHOLD_OFF = 24'd6000,
    parameter integer ATTACK_WINDOWS = 2,
    parameter integer RELEASE_WINDOWS = 16,
    parameter integer MIN_ACTIVE_WINDOWS = 82
) (
    input wire sys_clk,
    input wire pi_signal,
    input wire i2s_sd,
    output wire i2s_sck,
    output wire i2s_ws,
    output wire led
);
reg [POR_BITS-1:0] por_counter = {POR_BITS{1'b0}};
reg internal_reset_n = 1'b0;
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
wire sample_channel;
(* keep = "true" *) wire i2s_frame_error;
wire [23:0] magnitude;
wire frame_valid;
wire [23:0] energy;
wire sound_active;
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
audio_energy_detector_stable #(
    .WINDOW_LOG2(WINDOW_LOG2), .THRESHOLD_ON(THRESHOLD_ON),
    .THRESHOLD_OFF(THRESHOLD_OFF), .ATTACK_WINDOWS(ATTACK_WINDOWS),
    .RELEASE_WINDOWS(RELEASE_WINDOWS), .MIN_ACTIVE_WINDOWS(MIN_ACTIVE_WINDOWS)
) detector (
    .clk(sys_clk), .reset_n(internal_reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(sample_channel),
    .magnitude(magnitude), .frame_valid(frame_valid), .energy(energy),
    .sound_active(sound_active)
);

rasp_to_tang gpio17_baseline /* synthesis syn_hier = "hard" */ (
    .pi_signal(pi_signal), .led(gpio_led)
);
assign led = gpio_led | sound_active;
endmodule
