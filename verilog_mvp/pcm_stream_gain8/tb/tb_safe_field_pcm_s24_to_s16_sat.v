`timescale 1ns/1ps

module tb_safe_field_pcm_s24_to_s16_sat;
reg signed [23:0] sample_in;
wire signed [15:0] sample_out;
integer errors = 0;

safe_field_pcm_s24_to_s16_sat #(.SHIFT(5)) dut (
    .sample_in(sample_in),
    .sample_out(sample_out)
);

task check_sample;
    input signed [23:0] stimulus;
    input signed [15:0] expected;
    begin
        sample_in = stimulus;
        #1;
        if (sample_out !== expected) begin
            $display("FAIL convert input=%0d expected=%0d actual=%0d",
                     stimulus, expected, sample_out);
            errors = errors + 1;
        end else begin
            $display("PASS convert input=%0d expected=%0d actual=%0d",
                     stimulus, expected, sample_out);
        end
    end
endtask

initial begin
    // Force an initial transition so event-driven combinational simulators do
    // not leave the first zero-vector evaluation at X.
    sample_in = 24'shx;
    #1;
    check_sample(24'sd0, 16'sd0);
    check_sample(24'sd31, 16'sd0);
    check_sample(24'sd32, 16'sd1);
    check_sample(24'sd39519, 16'sd1234);       // 1234*32 + 31
    check_sample(-24'sd1, -16'sd1);
    check_sample(-24'sd32, -16'sd1);
    check_sample(-24'sd33, -16'sd2);
    check_sample(-24'sd39488, -16'sd1234);    // -1234*32
    check_sample(24'sd1048575, 16'sd32767);   // largest non-saturated result
    check_sample(-24'sd1048576, -16'sd32768); // exact negative endpoint
    check_sample(24'sd1048576, 16'sd32767);   // positive saturation boundary
    check_sample(-24'sd1048577, -16'sd32768); // negative saturation boundary
    check_sample(24'sh7FFFFF, 16'sd32767);    // positive full scale saturates
    check_sample(24'sh800000, -16'sd32768);   // negative full scale saturates

    if (errors == 0)
        $display("TEST_RESULT: PASS (signed >>>5, positive, negative, boundaries, saturation)");
    else
        $display("TEST_RESULT: FAIL errors=%0d", errors);
    $finish;
end
endmodule
