`timescale 1ns/1ps

// SAFE-FIELD MVP: frozen TP4 audio path plus versioned UART telemetry.
module safe_field_mvp_hw_bridge #(
    parameter integer POR_BITS = 8,
    parameter integer WINDOW_LOG2 = 8,
    parameter integer HALF_PERIOD_CLKS = 5,
    parameter [23:0] THRESHOLD_ON  = 24'd12000,
    parameter [23:0] THRESHOLD_OFF = 24'd6000,
    parameter integer ATTACK_WINDOWS = 24,
    parameter integer RELEASE_WINDOWS = 82,
    parameter integer UART_CLKS_PER_BIT = 234
) (
    input wire sys_clk,
    input wire pi_signal,
    input wire i2s_sd,
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
    end else internal_reset_n <= 1'b1;
end

wire capture_strobe;
wire [5:0] capture_bit_index;
wire signed [23:0] sample_data;
wire sample_valid;
wire sample_channel;
wire i2s_frame_error;
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
assign led = gpio_led | sound_active;

// One telemetry event per 256 complete stereo frames (about 164.8 events/s).
reg [31:0] frame_counter;
reg [WINDOW_LOG2-1:0] telemetry_window_count;
reg telemetry_pending;
reg telemetry_event_valid;
wire telemetry_event_ready;
reg telemetry_state;
reg [23:0] telemetry_energy;
reg [31:0] telemetry_frame_counter;
reg [7:0] telemetry_flags;
reg frame_error_latched;
reg sample_nonzero_latched;
reg telemetry_overrun_latched;

always @(posedge sys_clk or negedge internal_reset_n) begin
    if (!internal_reset_n) begin
        frame_counter <= 32'd0;
        telemetry_window_count <= {WINDOW_LOG2{1'b0}};
        telemetry_pending <= 1'b0;
        telemetry_event_valid <= 1'b0;
        telemetry_state <= 1'b0;
        telemetry_energy <= 24'd0;
        telemetry_frame_counter <= 32'd0;
        telemetry_flags <= 8'd0;
        frame_error_latched <= 1'b0;
        sample_nonzero_latched <= 1'b0;
        telemetry_overrun_latched <= 1'b0;
    end else begin
        telemetry_event_valid <= 1'b0;
        if (i2s_frame_error) frame_error_latched <= 1'b1;
        if (sample_valid && (sample_data != 0)) sample_nonzero_latched <= 1'b1;

        if (frame_valid) begin
            frame_counter <= frame_counter + 1'b1;
            if (&telemetry_window_count) begin
                telemetry_window_count <= {WINDOW_LOG2{1'b0}};
                if (telemetry_pending) telemetry_overrun_latched <= 1'b1;
                else telemetry_pending <= 1'b1;
            end else begin
                telemetry_window_count <= telemetry_window_count + 1'b1;
            end
        end

        // Capture one cycle after the energy window completes, so the FSM state
        // and energy correspond to the completed detector update.
        if (telemetry_pending && telemetry_event_ready) begin
            telemetry_state <= sound_active;
            telemetry_energy <= energy;
            telemetry_frame_counter <= frame_counter;
            telemetry_flags <= {4'd0, pi_signal, sample_nonzero_latched,
                                telemetry_overrun_latched, frame_error_latched};
            telemetry_event_valid <= 1'b1;
            telemetry_pending <= 1'b0;
        end
    end
end

safe_field_telemetry_tx #(.UART_CLKS_PER_BIT(UART_CLKS_PER_BIT)) telemetry (
    .clk(sys_clk), .reset_n(internal_reset_n),
    .event_valid(telemetry_event_valid), .event_ready(telemetry_event_ready),
    .event_state(telemetry_state), .event_energy(telemetry_energy),
    .event_frame_counter(telemetry_frame_counter), .event_flags(telemetry_flags),
    .uart_tx(uart_tx), .busy()
);
endmodule
