`timescale 1ns/1ps
module i2s_clock_gen #(
    parameter integer HALF_PERIOD_CLKS = 5
) (
    input wire clk,
    input wire reset_n,
    output reg i2s_sck,
    output reg i2s_ws,
    output reg capture_strobe,
    output reg [5:0] capture_bit_index
);
    integer div_count;
    always @(posedge clk or negedge reset_n) begin
        if (!reset_n) begin
            div_count <= 0; i2s_sck <= 1'b0; i2s_ws <= 1'b0;
            capture_strobe <= 1'b0; capture_bit_index <= 6'd0;
        end else begin
            capture_strobe <= 1'b0;
            if (div_count == HALF_PERIOD_CLKS-1) begin
                div_count <= 0; i2s_sck <= ~i2s_sck;
                if (!i2s_sck) begin
                    capture_strobe <= 1'b1;
                    if (capture_bit_index == 6'd63) capture_bit_index <= 6'd0;
                    else capture_bit_index <= capture_bit_index + 1'b1;
                    if (capture_bit_index == 6'd31) i2s_ws <= 1'b1;
                    else if (capture_bit_index == 6'd63) i2s_ws <= 1'b0;
                end
            end else div_count <= div_count + 1;
        end
    end
endmodule
