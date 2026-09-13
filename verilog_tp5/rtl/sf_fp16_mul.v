`timescale 1ns/1ps
// Binary16 academic multiplier. Subnormals are deliberately flushed to zero.
module sf_fp16_mul(input wire [15:0] a,input wire [15:0] b,output reg [15:0] result,output reg invalid,output reg overflow,output reg underflow);
reg sign;reg[4:0]ea,eb;reg[9:0]fa,fb;reg[10:0]ma,mb;reg[21:0]prod;integer exp_i;reg[9:0]frac_out;
 always @* begin sign=a[15]^b[15];ea=a[14:10];eb=b[14:10];fa=a[9:0];fb=b[9:0];ma=0;mb=0;prod=0;exp_i=0;frac_out=0;invalid=0;overflow=0;underflow=0;result=0;
if((ea==5'h1F&&fa!=0)||(eb==5'h1F&&fb!=0))begin result=16'h7E00;invalid=1;end
else if((ea==5'h1F&&eb==0&&fb==0)||(eb==5'h1F&&ea==0&&fa==0))begin result=16'h7E00;invalid=1;end
else if(ea==5'h1F||eb==5'h1F)result={sign,5'h1F,10'd0};
else if((ea==0&&fa==0)||(eb==0&&fb==0))result={sign,15'd0};
else if(ea==0||eb==0)begin result={sign,15'd0};underflow=1;end
else begin ma={1'b1,fa};mb={1'b1,fb};prod=ma*mb;exp_i=ea+eb-15;if(prod[21])begin exp_i=exp_i+1;frac_out=prod[20:11];end else frac_out=prod[19:10];if(exp_i>=31)begin result={sign,5'h1F,10'd0};overflow=1;end else if(exp_i<=0)begin result={sign,15'd0};underflow=1;end else result={sign,exp_i[4:0],frac_out};end end
endmodule
