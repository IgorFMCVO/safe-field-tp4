`timescale 1ns/1ps
module tb_uart_tx_byte;
localparam integer CLKS_PER_BIT = 8;
localparam integer CLOCK_PERIOD_NS = 10;
reg clk, reset_n, data_valid;
reg [7:0] data;
wire data_ready, uart_tx, busy;
integer checks, errors, bit_number;
reg [7:0] received;
time start_time;

uart_tx_byte #(.CLKS_PER_BIT(CLKS_PER_BIT)) dut (
    .clk(clk), .reset_n(reset_n), .data(data), .data_valid(data_valid),
    .data_ready(data_ready), .tx(uart_tx), .busy(busy)
);

initial begin clk=0; forever #(CLOCK_PERIOD_NS/2) clk=~clk; end
initial begin #10000; $display("FAIL testbench timeout"); $display("TEST_RESULT: FAIL"); $finish; end

task check_value;
    input [8*48-1:0] label_text;
    input [31:0] expected;
    input [31:0] obtained;
    begin
        checks=checks+1;
        if(obtained===expected) $display("PASS %-48s expected=%0d obtained=%0d",label_text,expected,obtained);
        else begin errors=errors+1; $display("FAIL %-48s expected=%0d obtained=%0d",label_text,expected,obtained); end
    end
endtask

initial begin
    checks=0; errors=0; reset_n=0; data_valid=0; data=8'hA5;
    repeat(3) @(posedge clk); reset_n=1; @(posedge clk); #1;
    check_value("idle line is HIGH",1,uart_tx);
    check_value("idle transmitter is ready",1,data_ready);
    @(negedge clk); data_valid=1;
    fork
        begin @(negedge clk); data_valid=0; end
        begin
            @(negedge uart_tx); start_time=$time;
            repeat(CLKS_PER_BIT/2) @(posedge clk); #1;
            check_value("start bit is LOW",0,uart_tx);
            for(bit_number=0;bit_number<8;bit_number=bit_number+1) begin
                repeat(CLKS_PER_BIT) @(posedge clk); #1;
                received[bit_number]=uart_tx;
            end
            repeat(CLKS_PER_BIT) @(posedge clk); #1;
            check_value("stop bit is HIGH",1,uart_tx);
        end
    join
    check_value("8 data bits are LSB-first",8'hA5,received);
    @(negedge busy);
    check_value("10-bit framing duration in ns",CLKS_PER_BIT*10*CLOCK_PERIOD_NS,$time-start_time);
    check_value("ready returns after stop bit",1,data_ready);
    $display("checks=%0d errors=%0d",checks,errors);
    if(errors==0)$display("TEST_RESULT: PASS");else $display("TEST_RESULT: FAIL");
    $finish;
end
endmodule
