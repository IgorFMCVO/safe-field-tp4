`timescale 1ns/1ps

// One physically relevant 16x16 signed multiplier. The 24-bit I2S sample is
// reduced to its most significant 16 bits before squaring, preserving sign.
// GowinSynthesis is explicitly directed to map the multiplier to one DSP.
module safe_field_audio_energy_dsp (
    input wire clk,
    input wire reset_n,
    input wire input_valid,
    input wire input_is_command,
    input wire signed [23:0] sample_signed,
    output reg result_valid,
    output reg result_is_command,
    output reg [31:0] sample_power
) /* synthesis syn_dspstyle = "dsp" */;
reg signed [15:0] sample_q;
reg valid_q;
reg command_q;

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        sample_q <= 16'sd0;
        valid_q <= 1'b0;
        command_q <= 1'b0;
        result_valid <= 1'b0;
        result_is_command <= 1'b0;
        sample_power <= 32'd0;
    end else begin
        sample_q <= sample_signed[23:8];
        valid_q <= input_valid;
        command_q <= input_is_command;
        result_valid <= valid_q;
        result_is_command <= command_q;
        if (valid_q)
            sample_power <= $signed(sample_q) * $signed(sample_q);
    end
end
endmodule
