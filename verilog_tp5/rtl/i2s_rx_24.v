`timescale 1ns/1ps
module i2s_rx_24 (
    input wire clk, input wire reset_n, input wire capture_strobe,
    input wire [5:0] capture_bit_index, input wire serial_data,
    output reg signed [23:0] sample_data, output reg sample_valid,
    output reg sample_channel, output reg frame_error
);
    reg [23:0] shift_reg;
    wire left_payload=(capture_bit_index>=6'd1)&&(capture_bit_index<=6'd24);
    wire right_payload=(capture_bit_index>=6'd33)&&(capture_bit_index<=6'd56);
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin shift_reg<=0;sample_data<=0;sample_valid<=0;sample_channel<=0;frame_error<=0;end
        else begin
            sample_valid<=0;frame_error<=0;
            if(capture_strobe) begin
                if(left_payload||right_payload) shift_reg<={shift_reg[22:0],serial_data};
                if(capture_bit_index==6'd24) begin sample_data<=$signed({shift_reg[22:0],serial_data});sample_channel<=0;sample_valid<=1;end
                else if(capture_bit_index==6'd56) begin sample_data<=$signed({shift_reg[22:0],serial_data});sample_channel<=1;sample_valid<=1;end
            end
        end
    end
endmodule
