`timescale 1ns/1ps

// DEBUG 5: static external-wiring level test.
//
// Each output phase lasts exactly PHASE_CLKS rising edges of the 27 MHz clock.
// With the hardware default of 54,000,000 clocks, pin 41 and pin 42 exchange
// LOW/HIGH levels every 2.000 seconds (full cycle: 4.000 seconds).
//
// i2s_sd is deliberately input-only.  The kept sampling register prevents the
// input path from being optimized away without ever feeding or driving pin 43.
module debug5_external_wiring_levels #(
    parameter integer POR_BITS = 8,
    parameter integer PHASE_CLKS = 54000000
) (
    input  wire sys_clk,
    input  wire pi_signal,
    input  wire i2s_sd,
    output wire i2s_sck,
    output wire i2s_ws,
    output wire led
);
reg [POR_BITS-1:0] por_count = {POR_BITS{1'b0}};
reg reset_n = 1'b0;
reg [25:0] phase_count = 26'd0;
reg phase = 1'b0;
(* keep = "true" *) reg i2s_sd_observed = 1'b0;

always @(posedge sys_clk) begin
    i2s_sd_observed <= i2s_sd;

    if (por_count != {POR_BITS{1'b1}}) begin
        por_count <= por_count + 1'b1;
        reset_n <= 1'b0;
    end else begin
        reset_n <= 1'b1;
    end
end

always @(posedge sys_clk) begin
    if (!reset_n) begin
        phase_count <= 26'd0;
        phase <= 1'b0;
    end else if (phase_count == PHASE_CLKS - 1) begin
        phase_count <= 26'd0;
        phase <= ~phase;
    end else begin
        phase_count <= phase_count + 1'b1;
    end
end

assign i2s_sck = phase;
assign i2s_ws = ~phase;

// Preserve the physically validated Raspberry GPIO17 HIGH override.
assign led = pi_signal | phase;
endmodule
