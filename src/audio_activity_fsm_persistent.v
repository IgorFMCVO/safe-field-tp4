`timescale 1ns/1ps

// Minimal temporal stabilization derived from the 99.42 s physical capture.
// Hysteresis thresholds are preserved; only consecutive-window qualification
// is applied.  No minimum hold or additional DSP/filter is present.
module audio_activity_fsm_persistent #(
    parameter [23:0] THRESHOLD_ON  = 24'd12000,
    parameter [23:0] THRESHOLD_OFF = 24'd6000,
    parameter integer ATTACK_WINDOWS = 24,
    parameter integer RELEASE_WINDOWS = 82
) (
    input wire clk,
    input wire reset_n,
    input wire energy_valid,
    input wire [23:0] energy,
    output reg sound_active
);
reg [7:0] attack_count;
reg [7:0] release_count;

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        sound_active <= 1'b0;
        attack_count <= 8'd0;
        release_count <= 8'd0;
    end else if (energy_valid) begin
        if (!sound_active) begin
            release_count <= 8'd0;
            if (energy >= THRESHOLD_ON) begin
                if (attack_count >= ATTACK_WINDOWS - 1) begin
                    sound_active <= 1'b1;
                    attack_count <= 8'd0;
                end else begin
                    attack_count <= attack_count + 1'b1;
                end
            end else begin
                attack_count <= 8'd0;
            end
        end else begin
            attack_count <= 8'd0;
            if (energy <= THRESHOLD_OFF) begin
                if (release_count >= RELEASE_WINDOWS - 1) begin
                    sound_active <= 1'b0;
                    release_count <= 8'd0;
                end else begin
                    release_count <= release_count + 1'b1;
                end
            end else begin
                release_count <= 8'd0;
            end
        end
    end
end
endmodule
