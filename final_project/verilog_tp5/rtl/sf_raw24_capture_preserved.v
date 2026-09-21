`timescale 1ns/1ps
// TP5 keeps the proven RAW24 acquisition/packet format isolated from the
// command path.  Names are prefixed so no frozen TP4 source is replaced.
module sf_raw24_i2s_clock_gen #(parameter integer HALF_PERIOD_CLKS=5, parameter integer SLOT_BITS=32)(
 input wire clk,input wire reset_n,output reg i2s_sck,output reg i2s_ws,
 output reg capture_strobe,output reg [5:0] capture_bit_index);
 reg [7:0] divider_count; reg [5:0] slot_bit_index;
 always @(posedge clk or negedge reset_n) begin
  if(!reset_n) begin divider_count<=0;slot_bit_index<=0;capture_bit_index<=0;capture_strobe<=0;i2s_sck<=0;i2s_ws<=0;end
  else begin capture_strobe<=0; if(divider_count==HALF_PERIOD_CLKS-1) begin divider_count<=0;
   if(!i2s_sck) begin i2s_sck<=1;capture_bit_index<=slot_bit_index;capture_strobe<=1;
    if(slot_bit_index==SLOT_BITS-1)slot_bit_index<=0;else slot_bit_index<=slot_bit_index+1'b1;
   end else begin i2s_sck<=0;if(slot_bit_index==0)i2s_ws<=~i2s_ws;end
  end else divider_count<=divider_count+1'b1; end
 end
endmodule

module sf_raw24_i2s_rx_24(input wire clk,input wire reset_n,input wire capture_strobe,
 input wire [5:0] capture_bit_index,input wire channel_ws,input wire serial_data,
 output reg signed [23:0] sample_data,output reg sample_valid,output reg sample_channel,output reg frame_error);
 reg [23:0] shift_register;reg [5:0] expected_bit_index;reg slot_channel;reg synchronized;
 always @(posedge clk or negedge reset_n) begin
  if(!reset_n) begin shift_register<=0;sample_data<=0;sample_valid<=0;sample_channel<=0;frame_error<=0;expected_bit_index<=0;slot_channel<=0;synchronized<=0;end
  else begin sample_valid<=0;frame_error<=0;if(capture_strobe) begin
   if(synchronized&&capture_bit_index!=expected_bit_index)frame_error<=1;
   synchronized<=1;if(capture_bit_index==31)expected_bit_index<=0;else expected_bit_index<=capture_bit_index+1'b1;
   if(capture_bit_index==0)slot_channel<=channel_ws;else if(channel_ws!=slot_channel)frame_error<=1;
   if(capture_bit_index>=1&&capture_bit_index<=24) begin shift_register<={shift_register[22:0],serial_data};
    if(capture_bit_index==24) begin sample_data<={shift_register[22:0],serial_data};sample_channel<=slot_channel;sample_valid<=1;end
   end
  end end
 end
endmodule

module sf_raw24_uart_tx_byte #(parameter integer CLKS_PER_BIT=18)(input wire clk,input wire reset_n,input wire [7:0] data,input wire data_valid,output wire data_ready,output reg tx,output reg busy);
 reg [31:0] baud_count;reg [3:0] bit_index;reg [7:0] data_latched;assign data_ready=~busy;
 always @(posedge clk or negedge reset_n) begin
  if(!reset_n)begin tx<=1;busy<=0;baud_count<=0;bit_index<=0;data_latched<=0;end
  else if(!busy)begin tx<=1;baud_count<=0;bit_index<=0;if(data_valid)begin data_latched<=data;tx<=0;busy<=1;end end
  else if(baud_count==CLKS_PER_BIT-1)begin baud_count<=0;case(bit_index)
   0:begin tx<=data_latched[0];bit_index<=1;end 1:begin tx<=data_latched[1];bit_index<=2;end
   2:begin tx<=data_latched[2];bit_index<=3;end 3:begin tx<=data_latched[3];bit_index<=4;end
   4:begin tx<=data_latched[4];bit_index<=5;end 5:begin tx<=data_latched[5];bit_index<=6;end
   6:begin tx<=data_latched[6];bit_index<=7;end 7:begin tx<=data_latched[7];bit_index<=8;end
   8:begin tx<=1;bit_index<=9;end default:begin tx<=1;busy<=0;bit_index<=0;end endcase
  end else baud_count<=baud_count+1'b1;
 end
endmodule

module sf_raw24_pcm_s24_to_s16_sat #(parameter integer SHIFT=5)(input wire signed [23:0] sample_in,output reg signed [15:0] sample_out);
 localparam signed [23:0] PCM16_MAX=24'sd32767,PCM16_MIN=-24'sd32768;wire signed [23:0] shifted_sample=sample_in>>>SHIFT;
 always @* begin if(shifted_sample>PCM16_MAX)sample_out=16'sh7fff;else if(shifted_sample<PCM16_MIN)sample_out=16'sh8000;else sample_out=shifted_sample[15:0];end
endmodule

// The RAW24 frame format and two-bank writer are preserved verbatim in
// behavior. tx_inhibit may only defer starting the next packet; it never
// gates I2S collection or truncates a packet already on the wire.
module sf_raw24_packet_tx #(parameter integer UART_CLKS_PER_BIT=18,parameter integer PCM_ARITH_SHIFT=5)(
 input wire clk,input wire reset_n,input wire signed [23:0] sample_data,input wire sample_valid,input wire sample_channel,input wire frame_error,input wire [5:0] status_flags,input wire tx_inhibit,
 output wire uart_tx,output wire busy,output wire tx_active,output reg [31:0] source_sample_count,output reg [31:0] accepted_sample_count,output reg [31:0] dropped_sample_count,output reg overrun_latched);
 localparam integer BLOCK_SAMPLES=16;localparam [6:0] LAST_BYTE_INDEX=94;
 reg signed [23:0] raw_bank0[0:15];reg signed [23:0] raw_bank1[0:15];
 reg signed [15:0] pcm_bank0[0:15];reg signed [15:0] pcm_bank1[0:15];
 reg[1:0]bank_full;reg write_bank,read_bank;reg[4:0]write_index;reg[31:0]bank_first_counter0,bank_first_counter1;reg[7:0]bank_flags0,bank_flags1;reg frame_error_sticky,decimation_phase;
 reg packet_sending,send_bank;reg[6:0]byte_index;reg[4:0]payload_sample_index;reg[2:0]payload_byte_in_pair;reg[15:0]next_sequence,packet_sequence,packet_crc;reg[31:0]packet_first_counter;reg[7:0]packet_flags,uart_data;reg signed[23:0]selected_raw24;reg signed[15:0]selected_pcm16;
 wire uart_ready,uart_busy,left_sample,retain_left_sample;wire signed[15:0]converted_pcm16;
 assign left_sample=sample_valid&&!sample_channel;
 assign retain_left_sample=left_sample&&!decimation_phase;
 sf_raw24_pcm_s24_to_s16_sat #(.SHIFT(PCM_ARITH_SHIFT)) converter(.sample_in(sample_data),.sample_out(converted_pcm16));
 function[15:0]crc16_update;input[15:0]crc_in;input[7:0]data_in;integer n;reg[15:0]c;begin c=crc_in^{data_in,8'h00};for(n=0;n<8;n=n+1)c=c[15]?((c<<1)^16'h1021):(c<<1);crc16_update=c;end endfunction
 always @* begin selected_raw24=0;selected_pcm16=0;if(byte_index>=13&&byte_index<=92)begin if(send_bank)begin selected_raw24=raw_bank1[payload_sample_index];selected_pcm16=pcm_bank1[payload_sample_index];end else begin selected_raw24=raw_bank0[payload_sample_index];selected_pcm16=pcm_bank0[payload_sample_index];end end
  if(byte_index==0)uart_data=8'ha5;else if(byte_index==1)uart_data=8'hc4;else if(byte_index==2)uart_data=8'h01;else if(byte_index==3)uart_data=8'h21;else if(byte_index==4)uart_data=packet_sequence[7:0];else if(byte_index==5)uart_data=packet_sequence[15:8];else if(byte_index==6)uart_data=packet_first_counter[7:0];else if(byte_index==7)uart_data=packet_first_counter[15:8];else if(byte_index==8)uart_data=packet_first_counter[23:16];else if(byte_index==9)uart_data=packet_first_counter[31:24];else if(byte_index==10)uart_data=16;else if(byte_index==11)uart_data=2;else if(byte_index==12)uart_data=packet_flags;else if(byte_index>=13&&byte_index<=92)case(payload_byte_in_pair)0:uart_data=selected_raw24[7:0];1:uart_data=selected_raw24[15:8];2:uart_data=selected_raw24[23:16];3:uart_data=selected_pcm16[7:0];default:uart_data=selected_pcm16[15:8];endcase else if(byte_index==93)uart_data=packet_crc[7:0];else uart_data=packet_crc[15:8];end
 assign busy=packet_sending|uart_busy|(bank_full!=0);assign tx_active=packet_sending|uart_busy;
 sf_raw24_uart_tx_byte #(.CLKS_PER_BIT(UART_CLKS_PER_BIT)) byte_transmitter(.clk(clk),.reset_n(reset_n),.data(uart_data),.data_valid(packet_sending),.data_ready(uart_ready),.tx(uart_tx),.busy(uart_busy));
 always @(posedge clk or negedge reset_n) begin
  if(!reset_n)begin bank_full<=0;write_bank<=0;read_bank<=0;write_index<=0;bank_first_counter0<=0;bank_first_counter1<=0;bank_flags0<=0;bank_flags1<=0;frame_error_sticky<=0;decimation_phase<=0;packet_sending<=0;send_bank<=0;byte_index<=0;payload_sample_index<=0;payload_byte_in_pair<=0;next_sequence<=0;packet_sequence<=0;packet_first_counter<=0;packet_flags<=0;packet_crc<=16'hffff;source_sample_count<=0;accepted_sample_count<=0;dropped_sample_count<=0;overrun_latched<=0;end else begin
   if(frame_error)frame_error_sticky<=1;if(left_sample)begin source_sample_count<=source_sample_count+1'b1;decimation_phase<=~decimation_phase;if(retain_left_sample)begin if(!bank_full[write_bank])begin if(write_bank)begin raw_bank1[write_index]<=sample_data;pcm_bank1[write_index]<=converted_pcm16;end else begin raw_bank0[write_index]<=sample_data;pcm_bank0[write_index]<=converted_pcm16;end if(write_index==0)begin if(write_bank)bank_first_counter1<=source_sample_count;else bank_first_counter0<=source_sample_count;end accepted_sample_count<=accepted_sample_count+1'b1;if(write_index==15)begin bank_full[write_bank]<=1;if(write_bank)bank_flags1<={status_flags,overrun_latched,(frame_error_sticky|frame_error)};else bank_flags0<={status_flags,overrun_latched,(frame_error_sticky|frame_error)};write_index<=0;frame_error_sticky<=0;overrun_latched<=0;write_bank<=~write_bank;end else write_index<=write_index+1'b1;end else begin dropped_sample_count<=dropped_sample_count+1'b1;overrun_latched<=1;end end end
   if(!packet_sending)begin if(!tx_inhibit&&(bank_full[read_bank]||bank_full[~read_bank]))begin if(!bank_full[read_bank])send_bank<=~read_bank;else send_bank<=read_bank;if(bank_full[read_bank])begin packet_first_counter<=read_bank?bank_first_counter1:bank_first_counter0;packet_flags<=read_bank?bank_flags1:bank_flags0;end else begin packet_first_counter<=read_bank?bank_first_counter0:bank_first_counter1;packet_flags<=read_bank?bank_flags0:bank_flags1;end packet_sequence<=next_sequence;next_sequence<=next_sequence+1'b1;packet_crc<=16'hffff;byte_index<=0;payload_sample_index<=0;payload_byte_in_pair<=0;packet_sending<=1;end end else if(uart_ready)begin if(byte_index>=2&&byte_index<=92)packet_crc<=crc16_update(packet_crc,uart_data);if(byte_index>=13&&byte_index<=92)begin if(payload_byte_in_pair==4)begin payload_byte_in_pair<=0;payload_sample_index<=payload_sample_index+1'b1;end else payload_byte_in_pair<=payload_byte_in_pair+1'b1;end if(byte_index==LAST_BYTE_INDEX)begin packet_sending<=0;bank_full[send_bank]<=0;read_bank<=~send_bank;byte_index<=0;end else byte_index<=byte_index+1'b1;end
  end
 end
endmodule
