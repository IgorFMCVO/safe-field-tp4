`timescale 1ns/1ps

// Calibrated SAFE-FIELD detector with deterministic temporal qualification.
// Feature extraction is identical to audio_energy_detector: max magnitude per
// stereo frame and average over 2**WINDOW_LOG2 frames.  Only state control is
// strengthened to reject isolated noise and make real speech visible.
module audio_energy_detector_stable #(
    parameter integer WINDOW_LOG2 = 8,
    parameter [23:0] THRESHOLD_ON  = 24'd12000,
    parameter [23:0] THRESHOLD_OFF = 24'd6000,
    parameter integer ATTACK_WINDOWS = 2,
    parameter integer RELEASE_WINDOWS = 16,
    parameter integer MIN_ACTIVE_WINDOWS = 82
) (
    input wire clk,
    input wire reset_n,
    input wire signed [23:0] sample_data,
    input wire sample_valid,
    input wire sample_channel,
    output reg [23:0] magnitude,
    output reg frame_valid,
    output reg [23:0] energy,
    output wire sound_active
);
localparam integer ACCUMULATOR_WIDTH = 24 + WINDOW_LOG2 + 1;
localparam STATE_QUIET = 1'b0;
localparam STATE_ACTIVE = 1'b1;
reg [23:0] left_magnitude;
reg [WINDOW_LOG2-1:0] window_count;
reg [ACCUMULATOR_WIDTH-1:0] accumulator;
reg detector_state;
reg [7:0] attack_count;
reg [7:0] release_count;
reg [7:0] active_hold_count;

function [23:0] absolute_24;
    input signed [23:0] value;
    begin absolute_24 = value[23] ? ((~value) + 1'b1) : value; end
endfunction

wire [23:0] current_magnitude = absolute_24(sample_data);
wire [23:0] selected_magnitude = (left_magnitude >= current_magnitude)
                                ? left_magnitude : current_magnitude;
wire [ACCUMULATOR_WIDTH-1:0] extended_magnitude =
    {{(ACCUMULATOR_WIDTH-24){1'b0}}, selected_magnitude};
wire [ACCUMULATOR_WIDTH:0] sum_with_current =
    {1'b0, accumulator} + {1'b0, extended_magnitude};
wire [23:0] completed_average =
    sum_with_current[WINDOW_LOG2 + 23:WINDOW_LOG2];
assign sound_active = (detector_state == STATE_ACTIVE);

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        left_magnitude <= 24'd0;
        window_count <= {WINDOW_LOG2{1'b0}};
        accumulator <= {ACCUMULATOR_WIDTH{1'b0}};
        magnitude <= 24'd0;
        frame_valid <= 1'b0;
        energy <= 24'd0;
        detector_state <= STATE_QUIET;
        attack_count <= 8'd0;
        release_count <= 8'd0;
        active_hold_count <= 8'd0;
    end else begin
        frame_valid <= 1'b0;
        if (sample_valid) begin
            if (!sample_channel) begin
                left_magnitude <= current_magnitude;
            end else begin
                magnitude <= selected_magnitude;
                frame_valid <= 1'b1;
                if (&window_count) begin
                    energy <= completed_average;
                    window_count <= {WINDOW_LOG2{1'b0}};
                    accumulator <= {ACCUMULATOR_WIDTH{1'b0}};
                    if (detector_state == STATE_QUIET) begin
                        release_count <= 8'd0;
                        active_hold_count <= 8'd0;
                        if (completed_average >= THRESHOLD_ON) begin
                            if (attack_count >= ATTACK_WINDOWS - 1) begin
                                detector_state <= STATE_ACTIVE;
                                attack_count <= 8'd0;
                                active_hold_count <= MIN_ACTIVE_WINDOWS;
                            end else attack_count <= attack_count + 1'b1;
                        end else attack_count <= 8'd0;
                    end else begin
                        attack_count <= 8'd0;
                        if (active_hold_count != 0) begin
                            active_hold_count <= active_hold_count - 1'b1;
                            release_count <= 8'd0;
                        end else if (completed_average <= THRESHOLD_OFF) begin
                            if (release_count >= RELEASE_WINDOWS - 1) begin
                                detector_state <= STATE_QUIET;
                                release_count <= 8'd0;
                            end else release_count <= release_count + 1'b1;
                        end else release_count <= 8'd0;
                    end
                end else begin
                    window_count <= window_count + 1'b1;
                    accumulator <= accumulator + extended_magnitude;
                end
            end
        end
    end
end
endmodule
