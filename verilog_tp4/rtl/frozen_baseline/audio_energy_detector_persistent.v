`timescale 1ns/1ps

// Validated magnitude/energy path plus the capture-derived persistence FSM.
module audio_energy_detector_persistent #(
    parameter integer WINDOW_LOG2 = 8,
    parameter [23:0] THRESHOLD_ON  = 24'd12000,
    parameter [23:0] THRESHOLD_OFF = 24'd6000,
    parameter integer ATTACK_WINDOWS = 24,
    parameter integer RELEASE_WINDOWS = 82
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
reg [23:0] left_magnitude;
reg [WINDOW_LOG2-1:0] window_count;
reg [ACCUMULATOR_WIDTH-1:0] accumulator;
reg energy_valid;

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

audio_activity_fsm_persistent #(
    .THRESHOLD_ON(THRESHOLD_ON), .THRESHOLD_OFF(THRESHOLD_OFF),
    .ATTACK_WINDOWS(ATTACK_WINDOWS), .RELEASE_WINDOWS(RELEASE_WINDOWS)
) activity_fsm (
    .clk(clk), .reset_n(reset_n), .energy_valid(energy_valid),
    .energy(energy), .sound_active(sound_active)
);

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        left_magnitude <= 24'd0;
        window_count <= {WINDOW_LOG2{1'b0}};
        accumulator <= {ACCUMULATOR_WIDTH{1'b0}};
        magnitude <= 24'd0;
        frame_valid <= 1'b0;
        energy <= 24'd0;
        energy_valid <= 1'b0;
    end else begin
        frame_valid <= 1'b0;
        energy_valid <= 1'b0;
        if (sample_valid) begin
            if (!sample_channel) begin
                left_magnitude <= current_magnitude;
            end else begin
                magnitude <= selected_magnitude;
                frame_valid <= 1'b1;
                if (&window_count) begin
                    energy <= completed_average;
                    energy_valid <= 1'b1;
                    window_count <= {WINDOW_LOG2{1'b0}};
                    accumulator <= {ACCUMULATOR_WIDTH{1'b0}};
                end else begin
                    window_count <= window_count + 1'b1;
                    accumulator <= accumulator + extended_magnitude;
                end
            end
        end
    end
end
endmodule
