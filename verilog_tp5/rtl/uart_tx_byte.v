`timescale 1ns/1ps
module uart_tx_byte #(parameter integer CLKS_PER_BIT=234)(input wire clk,input wire reset_n,input wire start,input wire [7:0] data,output reg tx,output reg busy,output reg done);
localparam S_IDLE=0,S_START=1,S_DATA=2,S_STOP=3;reg [1:0] state;integer clk_count;reg [2:0] bit_index;reg [7:0] shift;
always @(posedge clk or negedge reset_n) begin
 if(!reset_n) begin state<=S_IDLE;tx<=1'b1;busy<=0;done<=0;clk_count<=0;bit_index<=0;shift<=0;end else begin done<=0;case(state)
 S_IDLE: begin tx<=1'b1;busy<=0;if(start) begin shift<=data;state<=S_START;busy<=1;clk_count<=0;end end
 S_START: begin tx<=1'b0;if(clk_count==CLKS_PER_BIT-1) begin clk_count<=0;state<=S_DATA;bit_index<=0;end else clk_count<=clk_count+1;end
 S_DATA: begin tx<=shift[bit_index];if(clk_count==CLKS_PER_BIT-1) begin clk_count<=0;if(bit_index==3'd7) state<=S_STOP;else bit_index<=bit_index+1'b1;end else clk_count<=clk_count+1;end
 S_STOP: begin tx<=1'b1;if(clk_count==CLKS_PER_BIT-1) begin clk_count<=0;state<=S_IDLE;busy<=0;done<=1;end else clk_count<=clk_count+1;end
 endcase end end
endmodule
