`timescale 1ns/1ps

// Final TP4 candidate: validated I2S acquisition and energy extraction with
// capture-derived temporal persistence. GPIO17 retains the baseline override.
`ifndef SAFE_FIELD_TP4_STABLE_MODULE
`define SAFE_FIELD_TP4_STABLE_MODULE safe_field_tp4_audio_stable
`endif
module `SAFE_FIELD_TP4_STABLE_MODULE #(
    parameter integer POR_BITS = 8,
    parameter integer WINDOW_LOG2 = 8,
    parameter integer HALF_PERIOD_CLKS = 5,
    parameter [23:0] THRESHOLD_ON  = 24'd12000,
    parameter [23:0] THRESHOLD_OFF = 24'd6000,
    parameter integer ATTACK_WINDOWS = 24,
    parameter integer RELEASE_WINDOWS = 82
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
wire sample_channel;
(* keep = "true" *) wire i2s_frame_error;
wire [23:0] magnitude;
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
audio_energy_detector_persistent #(
    .WINDOW_LOG2(WINDOW_LOG2), .THRESHOLD_ON(THRESHOLD_ON),
    .THRESHOLD_OFF(THRESHOLD_OFF), .ATTACK_WINDOWS(ATTACK_WINDOWS),
    .RELEASE_WINDOWS(RELEASE_WINDOWS)
) detector (
    .clk(sys_clk), .reset_n(internal_reset_n), .sample_data(sample_data),
    .sample_valid(sample_valid), .sample_channel(sample_channel),
    .magnitude(magnitude), .frame_valid(frame_valid), .energy(energy),
    .sound_active(sound_active)
);
rasp_to_tang gpio17_baseline (.pi_signal(pi_signal), .led(gpio_led));
`ifdef SAFE_FIELD_TP4_CUE_ONLY_LED
assign led = gpio_led;
`else
assign led = gpio_led | sound_active;
`endif

// Short final GAO validation: one observation per two energy windows gives
// 24.86 seconds at depth 2048. These latches do not affect functional outputs.
(* keep = "true" *) reg [13:0] calibrated_energy_q;
(* keep = "true" *) reg energy_overflow;
(* keep = "true" *) reg energy_capture_clock;
(* keep = "true" *) reg frame_error_latched;
(* keep = "true" *) reg sample_nonzero_latched;
reg [WINDOW_LOG2-1:0] observed_frame_count;
reg completed_window_phase;
reg capture_clock_pending;

always @(posedge sys_clk or negedge internal_reset_n) begin
    if (!internal_reset_n) begin
        calibrated_energy_q <= 14'd0;
        energy_overflow <= 1'b0;
        energy_capture_clock <= 1'b0;
        frame_error_latched <= 1'b0;
        sample_nonzero_latched <= 1'b0;
        observed_frame_count <= {WINDOW_LOG2{1'b0}};
        completed_window_phase <= 1'b0;
        capture_clock_pending <= 1'b0;
    end else begin
        energy_capture_clock <= 1'b0;
        if (capture_clock_pending) begin
            energy_capture_clock <= 1'b1;
            capture_clock_pending <= 1'b0;
        end
        if (i2s_frame_error) frame_error_latched <= 1'b1;
        if (sample_valid && (sample_data != 0)) sample_nonzero_latched <= 1'b1;
        if (frame_valid) begin
            if (&observed_frame_count) begin
                observed_frame_count <= {WINDOW_LOG2{1'b0}};
                completed_window_phase <= ~completed_window_phase;
                if (completed_window_phase) begin
                    calibrated_energy_q <= energy[17:4];
                    energy_overflow <= |energy[23:18];
                    capture_clock_pending <= 1'b1;
                end
            end else observed_frame_count <= observed_frame_count + 1'b1;
        end
    end
end
endmodule
`undef SAFE_FIELD_TP4_STABLE_MODULE
`ifdef SAFE_FIELD_TP4_CUE_ONLY_LED
`undef SAFE_FIELD_TP4_CUE_ONLY_LED
`endif
