`timescale 1ns/1ps

// Diagnostic-only tops. These modules intentionally keep the validated pin
// interface unchanged and are built into separate implementation directories.

module diagnostic_por #(
    parameter integer POR_BITS = 8
) (
    input  wire clk,
    output reg  reset_n = 1'b0
);
reg [POR_BITS-1:0] counter = {POR_BITS{1'b0}};

always @(posedge clk) begin
    if (counter != {POR_BITS{1'b1}}) begin
        counter <= counter + 1'b1;
        reset_n <= 1'b0;
    end else begin
        reset_n <= 1'b1;
    end
end
endmodule


// DEBUG 1: toggle once per 21,094 completed I2S frames. At 42,187.5 frames/s,
// two toggles make a 0.99999 Hz LED blink. A completed frame is recognized by
// the receiver's RIGHT sample_valid pulse, not by a free-running sys_clk count.
module debug_i2s_internal_activity #(
    parameter integer POR_BITS = 8,
    parameter integer FRAMES_PER_HALF_PERIOD = 21094
) (
    input  wire sys_clk,
    input  wire pi_signal,
    input  wire i2s_sd,
    output wire i2s_sck,
    output wire i2s_ws,
    output wire led
);
wire reset_n;
wire capture_strobe;
wire [5:0] capture_bit_index;
wire signed [23:0] sample_data;
wire sample_valid;
wire sample_channel;
(* keep = "true" *) wire frame_error;
reg [15:0] frame_count;
reg activity_blink;

diagnostic_por #(.POR_BITS(POR_BITS)) por (
    .clk(sys_clk),
    .reset_n(reset_n)
);

i2s_clock_gen clock_master (
    .clk(sys_clk),
    .reset_n(reset_n),
    .i2s_sck(i2s_sck),
    .i2s_ws(i2s_ws),
    .capture_strobe(capture_strobe),
    .capture_bit_index(capture_bit_index)
);

i2s_rx_24 receiver (
    .clk(sys_clk),
    .reset_n(reset_n),
    .capture_strobe(capture_strobe),
    .capture_bit_index(capture_bit_index),
    .channel_ws(i2s_ws),
    .serial_data(i2s_sd),
    .sample_data(sample_data),
    .sample_valid(sample_valid),
    .sample_channel(sample_channel),
    .frame_error(frame_error)
);

always @(posedge sys_clk or negedge reset_n) begin
    if (!reset_n) begin
        frame_count    <= 16'd0;
        activity_blink <= 1'b0;
    end else if (sample_valid && sample_channel) begin
        if (frame_count == FRAMES_PER_HALF_PERIOD - 1) begin
            frame_count    <= 16'd0;
            activity_blink <= ~activity_blink;
        end else begin
            frame_count <= frame_count + 1'b1;
        end
    end
end

// GPIO17 remains a diagnostic HIGH override; keep it LOW to observe audio.
assign led = pi_signal | activity_blink;
endmodule


// DEBUG 2: after the INMP441's 2^18-SCK startup interval, count raw SD edges
// in a ~38.8 ms window. Eight or more transitions retrigger a 500 ms LED hold.
// No I2S parsing, magnitude, average, or threshold logic is used here.
module debug_sd_transition_detect #(
    parameter integer POR_BITS = 8,
    parameter [18:0] STARTUP_SCK_EDGES = 19'd262144,
    parameter [20:0] WINDOW_CLKS = 21'd1048576,
    parameter [15:0] MIN_TRANSITIONS = 16'd8,
    parameter [23:0] LED_HOLD_CLKS = 24'd13500000
) (
    input  wire sys_clk,
    input  wire pi_signal,
    input  wire i2s_sd,
    output wire i2s_sck,
    output wire i2s_ws,
    output wire led
);
wire reset_n;
wire capture_strobe;
wire [5:0] capture_bit_index;
reg sd_meta;
reg sd_sync;
reg sd_previous;
(* keep = "true" *) reg startup_done;
reg [18:0] startup_count;
reg [20:0] window_count;
(* keep = "true" *) reg [15:0] transition_count;
reg [23:0] led_hold_count;
wire transition_now;
wire [16:0] transitions_with_current;

assign transition_now = sd_sync ^ sd_previous;
assign transitions_with_current = {1'b0, transition_count}
                                + {{16{1'b0}}, transition_now};

diagnostic_por #(.POR_BITS(POR_BITS)) por (
    .clk(sys_clk),
    .reset_n(reset_n)
);

i2s_clock_gen clock_master (
    .clk(sys_clk),
    .reset_n(reset_n),
    .i2s_sck(i2s_sck),
    .i2s_ws(i2s_ws),
    .capture_strobe(capture_strobe),
    .capture_bit_index(capture_bit_index)
);

always @(posedge sys_clk or negedge reset_n) begin
    if (!reset_n) begin
        sd_meta          <= 1'b0;
        sd_sync          <= 1'b0;
        sd_previous      <= 1'b0;
        startup_done     <= 1'b0;
        startup_count    <= 19'd0;
        window_count     <= 21'd0;
        transition_count <= 16'd0;
        led_hold_count   <= 24'd0;
    end else begin
        // The double sampler makes this raw-line diagnostic robust even though
        // it deliberately ignores the known I2S bit positions.
        sd_meta <= i2s_sd;
        sd_sync <= sd_meta;

        if (!startup_done) begin
            sd_previous <= sd_sync;
            if (capture_strobe) begin
                if (startup_count == STARTUP_SCK_EDGES - 1'b1) begin
                    startup_done     <= 1'b1;
                    startup_count    <= startup_count;
                    window_count     <= 21'd0;
                    transition_count <= 16'd0;
                end else begin
                    startup_count <= startup_count + 1'b1;
                end
            end
        end else begin
            sd_previous <= sd_sync;

            if (led_hold_count != 0)
                led_hold_count <= led_hold_count - 1'b1;

            if (transition_now && !(&transition_count))
                transition_count <= transition_count + 1'b1;

            if (window_count == WINDOW_CLKS - 1'b1) begin
                window_count     <= 21'd0;
                transition_count <= 16'd0;
                if (transitions_with_current >= {1'b0, MIN_TRANSITIONS})
                    led_hold_count <= LED_HOLD_CLKS;
            end else begin
                window_count <= window_count + 1'b1;
            end
        end
    end
end

assign led = pi_signal | (led_hold_count != 0);
endmodule


// DEBUG 3: use the production receiver, but bypass averaging and the FSM.
// Any LEFT sample with magnitude >512 retriggers a 500 ms LED hold.
module debug_nonzero_sample #(
    parameter integer POR_BITS = 8,
    parameter [23:0] SAMPLE_THRESHOLD = 24'd512,
    parameter [23:0] LED_HOLD_CLKS = 24'd13500000
) (
    input  wire sys_clk,
    input  wire pi_signal,
    input  wire i2s_sd,
    output wire i2s_sck,
    output wire i2s_ws,
    output wire led
);
wire reset_n;
wire capture_strobe;
wire [5:0] capture_bit_index;
(* keep = "true" *) wire signed [23:0] sample_data;
(* keep = "true" *) wire sample_valid;
wire sample_channel;
(* keep = "true" *) wire frame_error;
wire [23:0] sample_magnitude;
reg [23:0] led_hold_count;
(* keep = "true" *) reg [31:0] zero_sample_count;
(* keep = "true" *) reg [31:0] nonzero_sample_count;

assign sample_magnitude = sample_data[23] ? ((~sample_data) + 1'b1)
                                          : sample_data;

diagnostic_por #(.POR_BITS(POR_BITS)) por (
    .clk(sys_clk),
    .reset_n(reset_n)
);

i2s_clock_gen clock_master (
    .clk(sys_clk),
    .reset_n(reset_n),
    .i2s_sck(i2s_sck),
    .i2s_ws(i2s_ws),
    .capture_strobe(capture_strobe),
    .capture_bit_index(capture_bit_index)
);

i2s_rx_24 receiver (
    .clk(sys_clk),
    .reset_n(reset_n),
    .capture_strobe(capture_strobe),
    .capture_bit_index(capture_bit_index),
    .channel_ws(i2s_ws),
    .serial_data(i2s_sd),
    .sample_data(sample_data),
    .sample_valid(sample_valid),
    .sample_channel(sample_channel),
    .frame_error(frame_error)
);

always @(posedge sys_clk or negedge reset_n) begin
    if (!reset_n) begin
        led_hold_count       <= 24'd0;
        zero_sample_count    <= 32'd0;
        nonzero_sample_count <= 32'd0;
    end else begin
        if (led_hold_count != 0)
            led_hold_count <= led_hold_count - 1'b1;

        if (sample_valid && !sample_channel) begin
            if (sample_data == 0)
                zero_sample_count <= zero_sample_count + 1'b1;
            else
                nonzero_sample_count <= nonzero_sample_count + 1'b1;

            if (sample_magnitude > SAMPLE_THRESHOLD)
                led_hold_count <= LED_HOLD_CLKS;
        end
    end
end

assign led = pi_signal | (led_hold_count != 0);
endmodule


// DEBUG 4: production pipeline and frame averaging, with calibration-only
// thresholds. This wrapper does not modify safe_field_tp4 or its final build.
module debug_low_threshold_audio #(
    parameter integer POR_BITS = 8,
    parameter integer WINDOW_LOG2 = 8,
    parameter [23:0] THRESHOLD_ON = 24'd2000,
    parameter [23:0] THRESHOLD_OFF = 24'd1000
) (
    input  wire sys_clk,
    input  wire pi_signal,
    input  wire i2s_sd,
    output wire i2s_sck,
    output wire i2s_ws,
    output wire led
);
safe_field_tp4 #(
    .POR_BITS(POR_BITS),
    .WINDOW_LOG2(WINDOW_LOG2),
    .THRESHOLD_ON(THRESHOLD_ON),
    .THRESHOLD_OFF(THRESHOLD_OFF)
) pipeline (
    .sys_clk(sys_clk),
    .pi_signal(pi_signal),
    .i2s_sd(i2s_sd),
    .i2s_sck(i2s_sck),
    .i2s_ws(i2s_ws),
    .led(led)
);
endmodule
