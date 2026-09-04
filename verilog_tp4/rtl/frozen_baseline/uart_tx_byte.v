`timescale 1ns/1ps

// 8-N-1 UART byte transmitter. CLKS_PER_BIT=234 gives 115384.6 baud from
// 27 MHz (+0.160% relative to 115200 baud).
module uart_tx_byte #(
    parameter integer CLKS_PER_BIT = 234
) (
    input wire clk,
    input wire reset_n,
    input wire [7:0] data,
    input wire data_valid,
    output wire data_ready,
    output reg tx,
    output reg busy
);
reg [31:0] baud_count;
reg [3:0] bit_index;
reg [7:0] data_latched;

assign data_ready = ~busy;

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        tx <= 1'b1;
        busy <= 1'b0;
        baud_count <= 32'd0;
        bit_index <= 4'd0;
        data_latched <= 8'd0;
    end else if (!busy) begin
        tx <= 1'b1;
        baud_count <= 32'd0;
        bit_index <= 4'd0;
        if (data_valid) begin
            data_latched <= data;
            tx <= 1'b0;
            busy <= 1'b1;
        end
    end else if (baud_count == CLKS_PER_BIT - 1) begin
        baud_count <= 32'd0;
        case (bit_index)
            4'd0: begin tx <= data_latched[0]; bit_index <= 4'd1; end
            4'd1: begin tx <= data_latched[1]; bit_index <= 4'd2; end
            4'd2: begin tx <= data_latched[2]; bit_index <= 4'd3; end
            4'd3: begin tx <= data_latched[3]; bit_index <= 4'd4; end
            4'd4: begin tx <= data_latched[4]; bit_index <= 4'd5; end
            4'd5: begin tx <= data_latched[5]; bit_index <= 4'd6; end
            4'd6: begin tx <= data_latched[6]; bit_index <= 4'd7; end
            4'd7: begin tx <= data_latched[7]; bit_index <= 4'd8; end
            4'd8: begin tx <= 1'b1; bit_index <= 4'd9; end
            default: begin
                tx <= 1'b1;
                busy <= 1'b0;
                bit_index <= 4'd0;
            end
        endcase
    end else begin
        baud_count <= baud_count + 1'b1;
    end
end
endmodule
