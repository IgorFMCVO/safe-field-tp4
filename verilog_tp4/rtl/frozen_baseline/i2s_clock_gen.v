`timescale 1ns/1ps

// INMP441 clock master for the Tang Nano 4K 27 MHz oscillator.
// HALF_PERIOD_CLKS=5 gives SCK=27 MHz/(2*5)=2.7 MHz.
// 32 SCK cycles per channel and 64 per stereo frame give WS=42.1875 kHz.
module i2s_clock_gen #(
    parameter integer HALF_PERIOD_CLKS = 5,
    parameter integer SLOT_BITS = 32
) (
    input  wire       clk,
    input  wire       reset_n,
    output reg        i2s_sck,
    output reg        i2s_ws,
    output reg        capture_strobe,
    output reg  [5:0] capture_bit_index
);

reg [7:0] divider_count;
reg [5:0] slot_bit_index;

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        divider_count     <= 8'd0;
        slot_bit_index    <= 6'd0;
        capture_bit_index <= 6'd0;
        capture_strobe    <= 1'b0;
        i2s_sck           <= 1'b0;
        i2s_ws            <= 1'b0;
    end else begin
        capture_strobe <= 1'b0;

        if (divider_count == HALF_PERIOD_CLKS - 1) begin
            divider_count <= 8'd0;

            if (!i2s_sck) begin
                // Raise SCK. The receiver samples SD one clk later, safely
                // inside the SCK-high interval instead of on the output edge.
                i2s_sck           <= 1'b1;
                capture_bit_index <= slot_bit_index;
                capture_strobe    <= 1'b1;

                if (slot_bit_index == SLOT_BITS - 1)
                    slot_bit_index <= 6'd0;
                else
                    slot_bit_index <= slot_bit_index + 1'b1;
            end else begin
                // WS changes on the falling SCK edge preceding delay bit 0.
                // Therefore the MSB is captured on bit 1, as required by I2S.
                i2s_sck <= 1'b0;
                if (slot_bit_index == 0)
                    i2s_ws <= ~i2s_ws;
            end
        end else begin
            divider_count <= divider_count + 1'b1;
        end
    end
end

endmodule
