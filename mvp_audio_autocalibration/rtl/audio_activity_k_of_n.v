`timescale 1ns/1ps

// Runtime-configurable voice detector. A K-of-N vote tolerates the short
// below-threshold gaps that made the frozen consecutive-window detector miss
// ordinary speech. Release and hangover are separate and deterministic.
module audio_activity_k_of_n (
    input wire clk,
    input wire reset_n,
    input wire energy_valid,
    input wire [23:0] energy,
    input wire [23:0] threshold_on,
    input wire [23:0] threshold_off,
    input wire [5:0] cfg_k,
    input wire [5:0] cfg_n,
    input wire [7:0] attack_windows,
    input wire [7:0] release_windows,
    input wire [7:0] hangover_windows,
    output reg sound_active,
    output reg [5:0] vote_count
);
reg [31:0] history;
reg [7:0] attack_count;
reg [7:0] release_count;
reg [7:0] hangover_count;
integer i;
reg [5:0] votes_next;
reg [31:0] history_next;

always @* begin
    history_next = {history[30:0], (energy >= threshold_on)};
    votes_next = 6'd0;
    for (i = 0; i < 32; i = i + 1)
        if ((i < cfg_n) && history_next[i]) votes_next = votes_next + 1'b1;
end

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        history <= 32'd0;
        attack_count <= 8'd0;
        release_count <= 8'd0;
        hangover_count <= 8'd0;
        sound_active <= 1'b0;
        vote_count <= 6'd0;
    end else if (energy_valid) begin
        history <= history_next;
        vote_count <= votes_next;
        if (!sound_active) begin
            release_count <= 8'd0;
            hangover_count <= 8'd0;
            if (votes_next != 0) begin
                if ((votes_next >= cfg_k) &&
                    ((attack_windows == 0) || (attack_count >= attack_windows - 1'b1))) begin
                    sound_active <= 1'b1;
                    attack_count <= 8'd0;
                end else if (attack_count != 8'hFF) begin
                    attack_count <= attack_count + 1'b1;
                end
            end else begin
                attack_count <= 8'd0;
            end
        end else begin
            attack_count <= 8'd0;
            if (energy > threshold_off) begin
                release_count <= 8'd0;
                hangover_count <= 8'd0;
            end else if ((release_windows != 0) &&
                         (release_count < release_windows)) begin
                release_count <= release_count + 1'b1;
                hangover_count <= 8'd0;
            end else if ((hangover_windows != 0) &&
                         (hangover_count < hangover_windows)) begin
                hangover_count <= hangover_count + 1'b1;
            end else begin
                sound_active <= 1'b0;
                release_count <= 8'd0;
                hangover_count <= 8'd0;
                history <= 32'd0;
                vote_count <= 6'd0;
            end
        end
    end
end
endmodule
