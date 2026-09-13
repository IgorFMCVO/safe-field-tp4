`timescale 1ns/1ps
// TP5 final top: RAW24 remains the primary continuous acoustic path. The
// command responder borrows TX only after a complete RAW24 packet boundary.
module safe_field_tp5_top #(
 parameter integer POR_BITS=8,parameter integer HALF_PERIOD_CLKS=5,
 parameter integer WINDOW_LOG2=8,parameter[23:0]THRESHOLD_ON=24'd12000,
 parameter[23:0]THRESHOLD_OFF=24'd6000,parameter integer ATTACK_WINDOWS=24,
 parameter integer RELEASE_WINDOWS=82,parameter integer UART_CLKS_PER_BIT=18
)(input wire sys_clk,input wire pi_signal,input wire i2s_sd,input wire uart_rx,
 output wire i2s_sck,output wire i2s_ws,output wire led,output wire uart_tx);
 reg[POR_BITS-1:0]por_counter={POR_BITS{1'b0}};reg reset_n=0;
 always@(posedge sys_clk)if(&por_counter)reset_n<=1;else begin por_counter<=por_counter+1'b1;reset_n<=0;end

 wire capture_strobe;wire[5:0]capture_bit_index;wire signed[23:0]sample_data;
 wire sample_valid,sample_channel,i2s_frame_error;
 sf_raw24_i2s_clock_gen #(.HALF_PERIOD_CLKS(HALF_PERIOD_CLKS),.SLOT_BITS(32)) clock_master(
  .clk(sys_clk),.reset_n(reset_n),.i2s_sck(i2s_sck),.i2s_ws(i2s_ws),
  .capture_strobe(capture_strobe),.capture_bit_index(capture_bit_index));
 sf_raw24_i2s_rx_24 receiver(.clk(sys_clk),.reset_n(reset_n),.capture_strobe(capture_strobe),
  .capture_bit_index(capture_bit_index),.channel_ws(i2s_ws),.serial_data(i2s_sd),
  .sample_data(sample_data),.sample_valid(sample_valid),.sample_channel(sample_channel),.frame_error(i2s_frame_error));

 // Read-only audio observer: no activity decision gates RAW24 capture.
 wire[23:0]magnitude,energy;wire frame_valid,sound_active;
 audio_energy_detector #(.WINDOW_LOG2(WINDOW_LOG2),.THRESHOLD_ON(THRESHOLD_ON),.THRESHOLD_OFF(THRESHOLD_OFF),.ATTACK_WINDOWS(ATTACK_WINDOWS),.RELEASE_WINDOWS(RELEASE_WINDOWS)) energy_observer(
  .clk(sys_clk),.reset_n(reset_n),.sample_data(sample_data),.sample_valid(sample_valid),.sample_channel(sample_channel),.magnitude(magnitude),.frame_valid(frame_valid),.energy(energy),.sound_active(sound_active));

 wire command_valid;wire[7:0]command_id;wire[15:0]command_sequence;wire[31:0]command_payload;wire checksum_error,framing_error;
 reg uart_low_seen,command_seen,checksum_error_seen,framing_error_seen;
 reg response_pending,response_launched;wire raw_tx_active;wire raw_uart_tx;wire command_ready=!response_pending&&!raw_tx_active;
 sf_command_rx #(.UART_CLKS_PER_BIT(UART_CLKS_PER_BIT)) cmdrx(.clk(sys_clk),.reset_n(reset_n),.uart_rx(uart_rx),.command_ready(command_ready),.command_valid(command_valid),.command_id(command_id),.command_sequence(command_sequence),.command_payload(command_payload),.checksum_error(checksum_error),.framing_error(framing_error));

 // command_valid freezes admission of the next RAW24 packet. Existing packets
 // always finish, so the physical UART mux never switches during 8-N-1.
 wire raw_busy;wire[31:0]source_sample_count,accepted_sample_count,dropped_sample_count;wire transport_overrun;
 sf_raw24_packet_tx #(.UART_CLKS_PER_BIT(UART_CLKS_PER_BIT),.PCM_ARITH_SHIFT(5)) raw24_transport(
  .clk(sys_clk),.reset_n(reset_n),.sample_data(sample_data),.sample_valid(sample_valid),.sample_channel(sample_channel),.frame_error(i2s_frame_error),.status_flags({command_seen,checksum_error_seen,framing_error_seen,uart_low_seen,pi_signal,sound_active}),.tx_inhibit(response_pending|command_valid),.uart_tx(raw_uart_tx),.busy(raw_busy),.tx_active(raw_tx_active),.source_sample_count(source_sample_count),.accepted_sample_count(accepted_sample_count),.dropped_sample_count(dropped_sample_count),.overrun_latched(transport_overrun));

 wire signed[31:0]q15_result;wire q15_sat;wire[15:0]fp16_result;wire fp_invalid,fp_overflow,fp_underflow;
 sf_fixed_q15_mac q15(.a_q15(command_payload[31:16]),.b_q15(command_payload[15:0]),.acc_q15(0),.result_q15(q15_result),.saturated(q15_sat));
 sf_fp16_mul fp16(.a(command_payload[31:16]),.b(command_payload[15:0]),.result(fp16_result),.invalid(fp_invalid),.overflow(fp_overflow),.underflow(fp_underflow));
 reg[7:0]response_type,response_flags;reg[15:0]response_sequence;reg[31:0]response_data;reg[31:0]good_commands,crc_errors,framing_errors;
 wire telemetry_busy,telemetry_done,response_uart_tx;
 // event_valid is a one-clock launch pulse.  A held response_pending level used
 // directly here would retrigger one duplicate frame on the cycle after done.
 wire response_launch=response_pending&&!response_launched&&!raw_tx_active;
 sf_telemetry_tx #(.UART_CLKS_PER_BIT(UART_CLKS_PER_BIT)) response_tx(.clk(sys_clk),.reset_n(reset_n),.event_valid(response_launch),.event_type(response_type),.event_sequence(response_sequence),.event_data(response_data),.event_flags(response_flags),.uart_tx(response_uart_tx),.busy(telemetry_busy),.done(telemetry_done));
 always@(posedge sys_clk or negedge reset_n)begin
  if(!reset_n)begin response_pending<=0;response_launched<=0;response_type<=0;response_sequence<=0;response_data<=0;response_flags<=0;good_commands<=0;crc_errors<=0;framing_errors<=0;uart_low_seen<=0;command_seen<=0;checksum_error_seen<=0;framing_error_seen<=0;end
  else begin
   if(!uart_rx)uart_low_seen<=1;
   if(command_valid)command_seen<=1;
   if(checksum_error)checksum_error_seen<=1;
   if(framing_error)framing_error_seen<=1;
   if(checksum_error)crc_errors<=crc_errors+1'b1;if(framing_error)framing_errors<=framing_errors+1'b1;
   if(response_launch)response_launched<=1;
   if(telemetry_done)begin response_pending<=0;response_launched<=0;end
   if(command_valid&&command_ready)begin
    good_commands<=good_commands+1'b1;response_pending<=1;response_launched<=0;response_type<=command_id;response_sequence<=command_sequence;
    response_flags<={1'b0,i2s_frame_error,transport_overrun,q15_sat,fp_invalid,fp_overflow,fp_underflow,sound_active};
    case(command_id)
     8'h01:response_data<=32'h54503501;
     8'h10:response_data<=q15_result;
     8'h11:response_data<={16'd0,fp16_result};
     8'h20:response_data<=good_commands+1'b1;
     8'h21:response_data<={8'd0,energy};
     8'h22:response_data<=crc_errors;
     8'h23:response_data<=framing_errors;
     default:begin response_data<=32'hffffffff;response_flags[7]<=1;end
    endcase
   end
  end
 end
 assign uart_tx=raw_tx_active?raw_uart_tx:response_uart_tx;
 assign led=pi_signal; // neutral, validated GPIO17 mirror
endmodule
