`timescale 1ns/1ps
// UART 8N1: two-flop asynchronous input synchronizer. CLKS_PER_BIT >= 8.
module uart_rx_byte #(parameter integer CLKS_PER_BIT=234)(
 input wire clk,input wire reset_n,input wire rx,
 output reg[7:0]data,output reg valid,output reg framing_error);
localparam S_IDLE=0,S_START=1,S_DATA=2,S_STOP=3;
reg[1:0]state;reg rx_meta,rx_sync;integer clk_count;reg[2:0]bit_index;reg[7:0]shift;
always@(posedge clk or negedge reset_n)begin
 if(!reset_n)begin rx_meta<=1'b1;rx_sync<=1'b1;end
 else begin rx_meta<=rx;rx_sync<=rx_meta;end
end
always@(posedge clk or negedge reset_n)begin
 if(!reset_n)begin state<=S_IDLE;clk_count<=0;bit_index<=0;shift<=0;data<=0;valid<=0;framing_error<=0;end
 else begin
  valid<=0;framing_error<=0;
  case(state)
   S_IDLE:if(!rx_sync)begin state<=S_START;clk_count<=0;end
   S_START:begin
    if(clk_count==((CLKS_PER_BIT-1)/2))begin
     if(!rx_sync)begin state<=S_DATA;clk_count<=0;bit_index<=0;end
     else state<=S_IDLE;
    end else clk_count<=clk_count+1;
   end
   S_DATA:begin
    if(clk_count==CLKS_PER_BIT-1)begin
     clk_count<=0;shift[bit_index]<=rx_sync;
     if(bit_index==7)state<=S_STOP;else bit_index<=bit_index+1'b1;
    end else clk_count<=clk_count+1;
   end
   S_STOP:begin
    if(clk_count==CLKS_PER_BIT-1)begin
     clk_count<=0;
     if(rx_sync)begin data<=shift;valid<=1'b1;end else framing_error<=1'b1;
     state<=S_IDLE;
    end else clk_count<=clk_count+1;
   end
   default:begin state<=S_IDLE;clk_count<=0;end
  endcase
 end
end
endmodule
