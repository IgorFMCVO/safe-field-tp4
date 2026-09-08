`timescale 1ns/1ps
module audio_energy_detector #(
    parameter integer WINDOW_LOG2=8,
    parameter [23:0] THRESHOLD_ON=24'd12000,
    parameter [23:0] THRESHOLD_OFF=24'd6000,
    parameter integer ATTACK_WINDOWS=24,
    parameter integer RELEASE_WINDOWS=82
)(input wire clk,input wire reset_n,input wire signed [23:0] sample_data,input wire sample_valid,input wire sample_channel,output reg [23:0] magnitude,output reg frame_valid,output reg [23:0] energy,output reg sound_active);
    reg [WINDOW_LOG2-1:0] sample_count; reg [31+WINDOW_LOG2:0] sum_abs; integer attack_count; integer release_count; reg [23:0] mag_now; reg [31+WINDOW_LOG2:0] sum_next; reg [23:0] avg_next;
    always @* begin
        if(sample_data[23]) mag_now=(~sample_data[23:0])+1'b1; else mag_now=sample_data[23:0];
        sum_next=sum_abs+mag_now; avg_next=sum_next>>WINDOW_LOG2;
    end
    always @(posedge clk or negedge reset_n) begin
        if(!reset_n) begin sample_count<=0;sum_abs<=0;magnitude<=0;frame_valid<=0;energy<=0;sound_active<=0;attack_count<=0;release_count<=0;end
        else begin
            frame_valid<=0;
            if(sample_valid&&!sample_channel) begin
                magnitude<=mag_now;
                if(&sample_count) begin
                    energy<=avg_next;frame_valid<=1;sample_count<=0;sum_abs<=0;
                    if(!sound_active) begin release_count<=0;if(avg_next>=THRESHOLD_ON) begin if(attack_count+1>=ATTACK_WINDOWS) begin sound_active<=1;attack_count<=0;end else attack_count<=attack_count+1;end else attack_count<=0;end
                    else begin attack_count<=0;if(avg_next<=THRESHOLD_OFF) begin if(release_count+1>=RELEASE_WINDOWS) begin sound_active<=0;release_count<=0;end else release_count<=release_count+1;end else release_count<=0;end
                end else begin sample_count<=sample_count+1'b1;sum_abs<=sum_next;end
            end
        end
    end
endmodule
