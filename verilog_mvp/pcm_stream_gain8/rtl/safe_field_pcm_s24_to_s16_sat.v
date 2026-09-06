`timescale 1ns/1ps

// Signed INMP441 PCM conversion with explicit saturation.
//
// The validated transport used sample_in[23:8], equivalent to an arithmetic
// shift by 8.  SHIFT=5 retains three additional low-order bits, i.e. an 8x
// digital gain relative to that transport, without allowing signed wraparound.
module safe_field_pcm_s24_to_s16_sat #(
    parameter integer SHIFT = 5
) (
    input  wire signed [23:0] sample_in,
    output reg  signed [15:0] sample_out
);
localparam signed [23:0] PCM16_MAX = 24'sd32767;
localparam signed [23:0] PCM16_MIN = -24'sd32768;
wire signed [23:0] shifted_sample = sample_in >>> SHIFT;

always @* begin
    if (shifted_sample > PCM16_MAX)
        sample_out = 16'sh7FFF;
    else if (shifted_sample < PCM16_MIN)
        sample_out = 16'sh8000;
    else
        sample_out = shifted_sample[15:0];
end
endmodule

