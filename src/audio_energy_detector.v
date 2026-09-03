`timescale 1ns/1ps

// Deterministic audio feature extraction:
//   1. absolute magnitude for each signed 24-bit channel sample;
//   2. max(left, right) once per stereo frame (works with either INMP441 L/R);
//   3. average magnitude over 2**WINDOW_LOG2 frames;
//   4. two-state FSM with hysteresis for a stable sound indication.
module audio_energy_detector #(
    parameter integer WINDOW_LOG2 = 8,
    parameter [23:0] THRESHOLD_ON  = 24'd50000,
    parameter [23:0] THRESHOLD_OFF = 24'd30000
) (
    input  wire               clk,
    input  wire               reset_n,
    input  wire signed [23:0] sample_data,
    input  wire               sample_valid,
    input  wire               sample_channel,
    output reg  [23:0]        magnitude,
    output reg                frame_valid,
    output reg  [23:0]        energy,
    output wire               sound_active
);

localparam integer ACCUMULATOR_WIDTH = 24 + WINDOW_LOG2 + 1;
localparam STATE_QUIET  = 1'b0;
localparam STATE_ACTIVE = 1'b1;

reg [23:0] left_magnitude;
reg [WINDOW_LOG2-1:0] window_count;
reg [ACCUMULATOR_WIDTH-1:0] accumulator;
reg detector_state;

function [23:0] absolute_24;
    input signed [23:0] value;
    begin
        if (value[23])
            absolute_24 = (~value) + 1'b1;
        else
            absolute_24 = value;
    end
endfunction

wire [23:0] current_magnitude;
wire [23:0] selected_magnitude;
wire [ACCUMULATOR_WIDTH-1:0] extended_magnitude;
wire [ACCUMULATOR_WIDTH:0] sum_with_current;
wire [23:0] completed_average;

assign current_magnitude  = absolute_24(sample_data);
assign selected_magnitude = (left_magnitude >= current_magnitude)
                          ? left_magnitude : current_magnitude;
assign extended_magnitude = {{(ACCUMULATOR_WIDTH-24){1'b0}}, selected_magnitude};
assign sum_with_current    = {1'b0, accumulator} + {1'b0, extended_magnitude};
// Explicit slice documents the division by 2**WINDOW_LOG2 and avoids an
// intentional-width-truncation warning in GowinSynthesis.
assign completed_average   = sum_with_current[WINDOW_LOG2 + 23:WINDOW_LOG2];
assign sound_active        = (detector_state == STATE_ACTIVE);

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        left_magnitude <= 24'd0;
        window_count   <= {WINDOW_LOG2{1'b0}};
        accumulator    <= {ACCUMULATOR_WIDTH{1'b0}};
        magnitude      <= 24'd0;
        frame_valid    <= 1'b0;
        energy         <= 24'd0;
        detector_state <= STATE_QUIET;
    end else begin
        frame_valid <= 1'b0;

        if (sample_valid) begin
            if (!sample_channel) begin
                left_magnitude <= current_magnitude;
            end else begin
                magnitude   <= selected_magnitude;
                frame_valid <= 1'b1;

                if (&window_count) begin
                    energy      <= completed_average;
                    window_count <= {WINDOW_LOG2{1'b0}};
                    accumulator <= {ACCUMULATOR_WIDTH{1'b0}};

                    case (detector_state)
                        STATE_QUIET: begin
                            if (completed_average >= THRESHOLD_ON)
                                detector_state <= STATE_ACTIVE;
                        end
                        STATE_ACTIVE: begin
                            if (completed_average <= THRESHOLD_OFF)
                                detector_state <= STATE_QUIET;
                        end
                        default: detector_state <= STATE_QUIET;
                    endcase
                end else begin
                    window_count <= window_count + 1'b1;
                    accumulator  <= accumulator + extended_magnitude;
                end
            end
        end
    end
end

endmodule
