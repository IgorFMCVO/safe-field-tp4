`timescale 1ns/1ps
// One 12-byte command-response frame. done is a one-clock completion pulse so
// a held request cannot be transmitted twice.
module sf_telemetry_tx #(parameter integer UART_CLKS_PER_BIT=18)(input wire clk,input wire reset_n,input wire event_valid,input wire[7:0]event_type,input wire[15:0]event_sequence,input wire[31:0]event_data,input wire[7:0]event_flags,output wire uart_tx,output reg busy,output reg done);
 reg[7:0]frame[0:11];reg[3:0]byte_index;reg tx_start;reg[7:0]tx_data;wire tx_busy,tx_done;
 function[7:0]crc8_next;input[7:0]current,value;integer i;reg[7:0]c;begin c=current^value;for(i=0;i<8;i=i+1)c=c[7]?((c<<1)^8'h07):(c<<1);crc8_next=c;end endfunction
 function[7:0]crc_frame;input[7:0]b2,b3,b4,b5,b6,b7,b8,b9,b10;reg[7:0]c;begin c=0;c=crc8_next(c,b2);c=crc8_next(c,b3);c=crc8_next(c,b4);c=crc8_next(c,b5);c=crc8_next(c,b6);c=crc8_next(c,b7);c=crc8_next(c,b8);c=crc8_next(c,b9);c=crc8_next(c,b10);crc_frame=c;end endfunction
 uart_tx_byte #(.CLKS_PER_BIT(UART_CLKS_PER_BIT)) tx0(.clk(clk),.reset_n(reset_n),.start(tx_start),.data(tx_data),.tx(uart_tx),.busy(tx_busy),.done(tx_done));
 always@(posedge clk or negedge reset_n)begin
  if(!reset_n)begin busy<=0;done<=0;byte_index<=0;tx_start<=0;tx_data<=0;end else begin tx_start<=0;done<=0;
   if(!busy&&event_valid)begin frame[0]<=8'h5a;frame[1]<=8'ha5;frame[2]<=8'h05;frame[3]<=event_type;frame[4]<=event_sequence[15:8];frame[5]<=event_sequence[7:0];frame[6]<=event_data[31:24];frame[7]<=event_data[23:16];frame[8]<=event_data[15:8];frame[9]<=event_data[7:0];frame[10]<=event_flags;frame[11]<=crc_frame(8'h05,event_type,event_sequence[15:8],event_sequence[7:0],event_data[31:24],event_data[23:16],event_data[15:8],event_data[7:0],event_flags);busy<=1;byte_index<=0;end
   else if(busy)begin if(tx_done)begin if(byte_index==11)begin busy<=0;done<=1;byte_index<=0;end else byte_index<=byte_index+1'b1;end else if(!tx_busy&&!tx_start)begin tx_data<=frame[byte_index];tx_start<=1;end end
  end
 end
endmodule
