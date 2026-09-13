`timescale 1ns/1ps
module tb_arithmetic;
reg signed[15:0]a,b;reg signed[31:0]acc;wire signed[31:0]qres;wire qsat;
reg[15:0]fa,fb;wire[15:0]fres;wire finv,fovf,funf;integer checks=0,fails=0;
sf_fixed_q15_mac q(.a_q15(a),.b_q15(b),.acc_q15(acc),.result_q15(qres),.saturated(qsat));
sf_fp16_mul f(.a(fa),.b(fb),.result(fres),.invalid(finv),.overflow(fovf),.underflow(funf));
task check_q;
 input signed[15:0]ta,tb;input signed[31:0]tacc,expected;input expected_sat;
 begin a=ta;b=tb;acc=tacc;#1;checks=checks+1;
 if(qres!==expected||qsat!==expected_sat)begin
 $display("FAIL fixed a=%0d b=%0d acc=%0d got=%0d expected=%0d",ta,tb,tacc,qres,expected);fails=fails+1;end end
endtask
task check_f;
 input[15:0]ta,tb,expected;input ei,eo,eu;
 begin fa=ta;fb=tb;#1;checks=checks+1;
 if(fres!==expected||finv!==ei||fovf!==eo||funf!==eu)begin
 $display("FAIL binary16 a=%h b=%h got=%h expected=%h",ta,tb,fres,expected);fails=fails+1;end end
endtask
initial begin
 $dumpfile("build/tb_arithmetic.vcd");$dumpvars(0,tb_arithmetic);
 a=0;b=0;acc=0;fa=0;fb=0;
 check_q(0,0,0,0,0);
 check_q(16'sh4000,16'sh4000,0,32'sd8192,0);
 check_q(-16'sh4000,16'sh4000,0,-32'sd8192,0);
 check_q(16'sh7fff,16'sh7fff,0,32'sd32766,0);
 // Widened 32-bit result: +1.0 is representable.
 check_q(16'sh8000,16'sh8000,0,32'sd32768,0);
 // Upper boundary T-1, T, T+1.
 check_q(16'sh4000,16'sh4000,32'sh7fffdffe,32'sh7ffffffe,0);
 check_q(16'sh4000,16'sh4000,32'sh7fffdfff,32'sh7fffffff,0);
 check_q(16'sh4000,16'sh4000,32'sh7fffe000,32'sh7fffffff,1);
 // Lower boundary T+1, T, T-1.
 check_q(-16'sh4000,16'sh4000,32'sh80002001,32'sh80000001,0);
 check_q(-16'sh4000,16'sh4000,32'sh80002000,32'sh80000000,0);
 check_q(-16'sh4000,16'sh4000,32'sh80001fff,32'sh80000000,1);
 // Binary16 academic policy: truncation and flush-to-zero, not full IEEE 754.
 check_f(16'h3E00,16'h4000,16'h4200,0,0,0);
 check_f(16'hC000,16'h3800,16'hBC00,0,0,0);
 check_f(16'h0000,16'h4500,16'h0000,0,0,0);
 check_f(16'h8000,16'h4500,16'h8000,0,0,0);
 check_f(16'h7BFF,16'h4000,16'h7C00,0,1,0);
 check_f(16'hFBFF,16'h4000,16'hFC00,0,1,0);
 check_f(16'h7C00,16'h0000,16'h7E00,1,0,0);
 check_f(16'h7E00,16'h3C00,16'h7E00,1,0,0);
 check_f(16'hFC00,16'hBC00,16'h7C00,0,0,0);
 check_f(16'h0001,16'h3C00,16'h0000,0,0,1);
 check_f(16'h0400,16'h3800,16'h0000,0,0,1);
 check_f(16'h8400,16'h3800,16'h8000,0,0,1);
 if(fails!=0)$fatal(1,"TEST_RESULT: FAIL arithmetic checks=%0d failures=%0d",checks,fails);
 $display("TEST_RESULT: PASS arithmetic checks=%0d",checks);$finish;
end
endmodule
