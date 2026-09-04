`timescale 1ns/1ps

// Pi -> Tang command protocol v1, fixed 11-byte packet:
// A6 6A | version | command | seq16 | payload32 | CRC-8/ATM.
module safe_field_command_rx #(
    parameter integer UART_CLKS_PER_BIT = 234
) (
    input wire clk,
    input wire reset_n,
    input wire uart_rx,
    output reg command_valid,
    output reg [7:0] command_id,
    output reg [15:0] command_sequence,
    output reg [31:0] command_payload,
    output reg checksum_error,
    output wire framing_error
);
wire [7:0] rx_data;
wire rx_valid;
wire rx_framing_error;
reg [3:0] byte_index;
reg [7:0] version_q;
reg [7:0] command_q;
reg [15:0] sequence_q;
reg [31:0] payload_q;
reg [7:0] crc_q;

function [7:0] crc8_update;
    input [7:0] crc_in;
    input [7:0] data_in;
    integer i;
    reg [7:0] c;
    begin
        c = crc_in ^ data_in;
        for (i = 0; i < 8; i = i + 1)
            c = c[7] ? ((c << 1) ^ 8'h07) : (c << 1);
        crc8_update = c;
    end
endfunction

uart_rx_byte #(.CLKS_PER_BIT(UART_CLKS_PER_BIT)) receiver (
    .clk(clk), .reset_n(reset_n), .rx(uart_rx), .data(rx_data),
    .data_valid(rx_valid), .framing_error(rx_framing_error)
);
assign framing_error = rx_framing_error;

always @(posedge clk or negedge reset_n) begin
    if (!reset_n) begin
        byte_index <= 4'd0;
        version_q <= 8'd0;
        command_q <= 8'd0;
        sequence_q <= 16'd0;
        payload_q <= 32'd0;
        crc_q <= 8'd0;
        command_valid <= 1'b0;
        command_id <= 8'd0;
        command_sequence <= 16'd0;
        command_payload <= 32'd0;
        checksum_error <= 1'b0;
    end else begin
        command_valid <= 1'b0;
        checksum_error <= 1'b0;
        if (rx_framing_error) begin
            byte_index <= 4'd0;
            checksum_error <= 1'b1;
        end else if (rx_valid) begin
            case (byte_index)
                4'd0: if (rx_data == 8'hA6) byte_index <= 4'd1;
                4'd1: begin
                    if (rx_data == 8'h6A) byte_index <= 4'd2;
                    else if (rx_data != 8'hA6) byte_index <= 4'd0;
                end
                4'd2: begin version_q <= rx_data; crc_q <= crc8_update(8'h00, rx_data); byte_index <= 4'd3; end
                4'd3: begin command_q <= rx_data; crc_q <= crc8_update(crc_q, rx_data); byte_index <= 4'd4; end
                4'd4: begin sequence_q[7:0] <= rx_data; crc_q <= crc8_update(crc_q, rx_data); byte_index <= 4'd5; end
                4'd5: begin sequence_q[15:8] <= rx_data; crc_q <= crc8_update(crc_q, rx_data); byte_index <= 4'd6; end
                4'd6: begin payload_q[7:0] <= rx_data; crc_q <= crc8_update(crc_q, rx_data); byte_index <= 4'd7; end
                4'd7: begin payload_q[15:8] <= rx_data; crc_q <= crc8_update(crc_q, rx_data); byte_index <= 4'd8; end
                4'd8: begin payload_q[23:16] <= rx_data; crc_q <= crc8_update(crc_q, rx_data); byte_index <= 4'd9; end
                4'd9: begin payload_q[31:24] <= rx_data; crc_q <= crc8_update(crc_q, rx_data); byte_index <= 4'd10; end
                default: begin
                    if ((rx_data == crc_q) && (version_q == 8'h01)) begin
                        command_id <= command_q;
                        command_sequence <= sequence_q;
                        command_payload <= payload_q;
                        command_valid <= 1'b1;
                    end else checksum_error <= 1'b1;
                    byte_index <= 4'd0;
                end
            endcase
        end
    end
end
endmodule
