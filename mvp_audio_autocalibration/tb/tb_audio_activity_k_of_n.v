`timescale 1ns/1ps

module tb_audio_activity_k_of_n;
reg clk = 0;
reg reset_n = 0;
reg energy_valid = 0;
reg [23:0] energy = 0;
wire sound_active;
wire [5:0] vote_count;
integer failures = 0;

always #5 clk = ~clk;
audio_activity_k_of_n dut (
    .clk(clk), .reset_n(reset_n), .energy_valid(energy_valid), .energy(energy),
    .threshold_on(24'd1000), .threshold_off(24'd500),
    .cfg_k(6'd3), .cfg_n(6'd5), .attack_windows(8'd1),
    .release_windows(8'd2), .hangover_windows(8'd3),
    .sound_active(sound_active), .vote_count(vote_count)
);

task sample;
    input [23:0] value;
    begin
        @(negedge clk); energy = value; energy_valid = 1;
        @(negedge clk); energy_valid = 0;
    end
endtask

task expect_state;
    input expected;
    input [127:0] label;
    begin
        if (sound_active !== expected) begin
            $display("FAIL %0s expected=%0d actual=%0d votes=%0d", label,
                     expected, sound_active, vote_count);
            failures = failures + 1;
        end else $display("PASS %0s expected=%0d actual=%0d votes=%0d", label,
                          expected, sound_active, vote_count);
    end
endtask

initial begin
    repeat (4) @(negedge clk);
    reset_n = 1;
    repeat (8) sample(24'd100);
    expect_state(0, "silence");
    sample(24'd1500); sample(24'd100); sample(24'd1600);
    expect_state(0, "two_of_five");
    sample(24'd200); sample(24'd1700);
    expect_state(1, "three_of_five");
    sample(24'd200); sample(24'd1400); sample(24'd100);
    expect_state(1, "speech_gap_tolerated");
    sample(24'd100); sample(24'd100); sample(24'd100); sample(24'd100);
    expect_state(1, "release_hangover");
    sample(24'd100); sample(24'd100);
    expect_state(0, "quiet_recovered");
    if (failures == 0) $display("PASS tb_audio_activity_k_of_n");
    else $display("FAIL tb_audio_activity_k_of_n failures=%0d", failures);
    $finish;
end
endmodule
