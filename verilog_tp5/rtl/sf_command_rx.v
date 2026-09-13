`timescale 1ns/1ps
module sf_command_rx #(parameter integer UART_CLKS_PER_BIT=234)(input wire clk,input wire reset_n,input wire uart_rx,input wire command_ready,output reg command_valid,output reg [7:0] command_id,output reg [15:0] command_sequence,output reg [31:0] command_payload,output reg checksum_error,output wire framing_error);
wire [7:0] rx_byte;wire rx_valid;uart_rx_byte #(.CLKS_PER_BIT(UART_CLKS_PER_BIT)) rx0(.clk(clk),.reset_n(reset_n),.rx(uart_rx),.data(rx_byte),.valid(rx_valid),.framing_error(framing_error));
reg [3:0] index;reg [7:0] crc;reg [7:0] cmd_tmp;reg [15:0] seq_tmp;reg [31:0] payload_tmp;
function [7:0] crc8_next;input [7:0] current;input [7:0] value;integer i;reg [7:0] c;begin c=current^value;for(i=0;i<8;i=i+1)c=c[7]?((c<<1)^8'h07):(c<<1);crc8_next=c;end endfunction
always @(posedge clk or negedge reset_n) begin
 if(!reset_n) begin index<=0;crc<=0;command_valid<=0;command_id<=0;command_sequence<=0;command_payload<=0;checksum_error<=0;cmd_tmp<=0;seq_tmp<=0;payload_tmp<=0;end else begin
 checksum_error<=0;if(command_valid&&command_ready)command_valid<=0;
 if(rx_valid&&!command_valid)case(index)
 0:if(rx_byte==8'hA6)index<=1;else index<=0;
 1:begin if(rx_byte==8'h6A)begin index<=2;crc<=0;end else if(rx_byte==8'hA6)index<=1;else index<=0;end
 2:begin if(rx_byte==8'h05)begin crc<=crc8_next(0,rx_byte);index<=3;end else index<=0;end
 3:begin cmd_tmp<=rx_byte;crc<=crc8_next(crc,rx_byte);index<=4;end
 4:begin seq_tmp[15:8]<=rx_byte;crc<=crc8_next(crc,rx_byte);index<=5;end
 5:begin seq_tmp[7:0]<=rx_byte;crc<=crc8_next(crc,rx_byte);index<=6;end
 6:begin payload_tmp[31:24]<=rx_byte;crc<=crc8_next(crc,rx_byte);index<=7;end
 7:begin payload_tmp[23:16]<=rx_byte;crc<=crc8_next(crc,rx_byte);index<=8;end
 8:begin payload_tmp[15:8]<=rx_byte;crc<=crc8_next(crc,rx_byte);index<=9;end
 9:begin payload_tmp[7:0]<=rx_byte;crc<=crc8_next(crc,rx_byte);index<=10;end
 10:begin if(rx_byte==crc)begin command_id<=cmd_tmp;command_sequence<=seq_tmp;command_payload<=payload_tmp;command_valid<=1'b1;end else checksum_error<=1'b1;index<=0;end
 default:index<=0;endcase end end
endmodule
