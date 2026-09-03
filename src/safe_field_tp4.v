`timescale 1ns/1ps

module safe_field_tp4 #(
    parameter integer POR_BITS = 8,
    parameter integer WINDOW_LOG2 = 8,
    parameter [23:0] THRESHOLD_ON  = 24'd50000,
    parameter [23:0] THRESHOLD_OFF = 24'd30000
) (
    input  wire sys_clk,
    input  wire pi_signal,
    input  wire i2s_sd,
    output wire i2s_sck,
    output wire i2s_ws,
    output wire led
);

// The Gowin bitstream initializes these registers. The counter then holds all
// synchronous audio logic in reset for 2**POR_BITS input-clock cycles.
reg [POR_BITS-1:0] por_counter = {POR_BITS{1'b0}};
reg internal_reset_n = 1'b0;

always @(posedge sys_clk) begin
    if (por_counter != {POR_BITS{1'b1}}) begin
        por_counter      <= por_counter + 1'b1;
        internal_reset_n <= 1'b0;
    end else begin
        internal_reset_n <= 1'b1;
    end
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

i2s_clock_gen clock_master (
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

audio_energy_detector #(
    .WINDOW_LOG2(WINDOW_LOG2),
    .THRESHOLD_ON(THRESHOLD_ON),
    .THRESHOLD_OFF(THRESHOLD_OFF)
) detector (
    .clk(sys_clk),
    .reset_n(internal_reset_n),
    .sample_data(sample_data),
    .sample_valid(sample_valid),
    .sample_channel(sample_channel),
    .magnitude(magnitude),
    .frame_valid(frame_valid),
    .energy(energy),
    .sound_active(sound_active)
);

// Preserve the exact validated Raspberry Pi GPIO17 -> Tang logic path.
rasp_to_tang gpio17_baseline /* synthesis syn_hier = "hard" */ (
    .pi_signal(pi_signal),
    .led(gpio_led)
);

// GPIO17 HIGH remains a diagnostic override. With GPIO17 LOW, the LED is the
// deterministic physical indication of audio energy crossing the threshold.
assign led = gpio_led | sound_active;

endmodule
