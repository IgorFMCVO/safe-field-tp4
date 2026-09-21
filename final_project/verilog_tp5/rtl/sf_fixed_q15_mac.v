`timescale 1ns/1ps
module sf_fixed_q15_mac(input wire signed [15:0] a_q15,input wire signed [15:0] b_q15,input wire signed [31:0] acc_q15,output reg signed [31:0] result_q15,output reg saturated);
reg signed [31:0] product;reg signed [63:0] scaled;reg signed [63:0] sum;
always @* begin product=a_q15*b_q15;scaled=$signed(product)>>>15;sum=scaled+$signed(acc_q15);saturated=1'b0;if(sum>64'sh000000007FFFFFFF)begin result_q15=32'sh7FFFFFFF;saturated=1'b1;end else if(sum < -64'sh0000000080000000)begin result_q15=32'sh80000000;saturated=1'b1;end else result_q15=sum[31:0];end
endmodule
