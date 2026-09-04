`timescale 1ns/1ps

// Physical-validation top. The production datapath and GPIO17 override are
// intentionally identical to safe_field_tp4; only passive GAO observability
// counters/toggles are added. This top is built to a separate .fs artifact.
module safe_field_tp4_gao #(
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
(* keep = "true" *) wire [23:0] magnitude;
(* keep = "true" *) wire frame_valid;
(* keep = "true" *) wire [23:0] energy;
(* keep = "true" *) wire sound_active;
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

rasp_to_tang gpio17_baseline /* synthesis syn_hier = "hard" */ (
    .pi_signal(pi_signal),
    .led(gpio_led)
);

assign led = gpio_led | sound_active;

// Passive observability registers. Saturating counters avoid ambiguity during
// a long JTAG session. Toggles preserve one-cycle events for the frame-rate AO.
(* keep = "true" *) reg sample_valid_toggle;
(* keep = "true" *) reg frame_valid_toggle;
(* keep = "true" *) reg energy_update_toggle;
(* keep = "true" *) reg i2s_frame_error_latched;
(* keep = "true" *) reg [15:0] left_sample_count;
(* keep = "true" *) reg [15:0] zero_left_count;
(* keep = "true" *) reg [15:0] nonzero_left_count;
(* keep = "true" *) reg [15:0] frame_error_count;
(* keep = "true" *) reg [15:0] sd_transition_count;
(* keep = "true" *) reg [WINDOW_LOG2-1:0] window_frame_count;

reg sd_meta;
reg sd_sync;
reg sd_previous;

always @(posedge sys_clk or negedge internal_reset_n) begin
    if (!internal_reset_n) begin
        sample_valid_toggle     <= 1'b0;
        frame_valid_toggle      <= 1'b0;
        energy_update_toggle    <= 1'b0;
        i2s_frame_error_latched <= 1'b0;
        left_sample_count       <= 16'd0;
        zero_left_count         <= 16'd0;
        nonzero_left_count      <= 16'd0;
        frame_error_count       <= 16'd0;
        sd_transition_count     <= 16'd0;
        window_frame_count      <= {WINDOW_LOG2{1'b0}};
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
            end else if (!(&nonzero_left_count)) begin
                nonzero_left_count <= nonzero_left_count + 1'b1;
            end
        end

        if (frame_valid) begin
            frame_valid_toggle <= ~frame_valid_toggle;
            if (&window_frame_count) begin
                window_frame_count   <= {WINDOW_LOG2{1'b0}};
                energy_update_toggle <= ~energy_update_toggle;
            end else begin
                window_frame_count <= window_frame_count + 1'b1;
            end
        end
    end
end

endmodule
