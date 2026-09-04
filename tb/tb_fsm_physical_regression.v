`timescale 1ns/1ps
module tb_fsm_physical_regression;
localparam TRACE_WORDS = 16384;
integer checks, errors, index, transitions, last_transition, rapid_reversals;
integer marker_run, events_total, events_detected;
reg clk, reset_n, energy_valid, marker, previous_marker, previous_state;
reg active_seen_in_marker;
reg [23:0] energy;
reg [24:0] trace_memory [0:TRACE_WORDS-1];
wire sound_active;

audio_activity_fsm_persistent #(
 .THRESHOLD_ON(24'd12000), .THRESHOLD_OFF(24'd6000),
 .ATTACK_WINDOWS(24), .RELEASE_WINDOWS(82)
) dut (.clk(clk), .reset_n(reset_n), .energy_valid(energy_valid),
 .energy(energy), .sound_active(sound_active));

initial begin clk=0; forever #5 clk=~clk; end
task check_integer; input [8*64-1:0] label_text; input integer expected; input integer obtained;
 begin checks=checks+1; if(obtained===expected) $display("PASS %-64s expected=%0d obtained=%0d",label_text,expected,obtained);
 else begin errors=errors+1; $display("FAIL %-64s expected=%0d obtained=%0d",label_text,expected,obtained); end end endtask

initial begin
 $readmemh("evidence/physical/retest_after_contact_fix/fsm_stabilization/physical_energy_99s.memh",trace_memory);
 checks=0;errors=0;transitions=0;last_transition=-100000;rapid_reversals=0;
 marker_run=0;events_total=0;events_detected=0;active_seen_in_marker=0;
 reset_n=0;energy_valid=0;energy=0;marker=0;previous_marker=0;previous_state=0;
 repeat(2) @(posedge clk); reset_n=1;
 for(index=0;index<TRACE_WORDS;index=index+1) begin
  @(negedge clk); marker=trace_memory[index][24];energy=trace_memory[index][23:0];energy_valid=1;
  @(posedge clk); #1;
  if(sound_active!=previous_state) begin
   transitions=transitions+1;
   if(index-last_transition<82) rapid_reversals=rapid_reversals+1;
   last_transition=index;previous_state=sound_active;
  end
  if(marker) begin marker_run=marker_run+1;if(sound_active)active_seen_in_marker=1;end
  if(previous_marker&&!marker) begin
   if(marker_run>=200) begin events_total=events_total+1;if(active_seen_in_marker)events_detected=events_detected+1;end
   marker_run=0;active_seen_in_marker=0;
  end
  previous_marker=marker;
 end
 energy_valid=0;
 check_integer("physical regression transitions reduced from 100",7,transitions);
 check_integer("no rapid reversal under 500 ms",0,rapid_reversals);
 check_integer("confirmed observable intervals in trace",9,events_total);
 check_integer("all confirmed intervals retain ACTIVE",9,events_detected);
 $display("REGRESSION_99S before=100 after=%0d events=%0d/%0d rapid=%0d",transitions,events_detected,events_total,rapid_reversals);
 $display("checks=%0d errors=%0d",checks,errors);
 if(errors==0)$display("TEST_RESULT: PASS");else $display("TEST_RESULT: FAIL");$finish;
end
endmodule
