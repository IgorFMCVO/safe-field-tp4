IVERILOG ?= iverilog
VVP ?= vvp
PYTHON ?= python3
BUILD := build
RTL := $(wildcard rtl/*.v)
CHECK := $(PYTHON) ../scripts/run_checked.py --timeout 30
.PHONY: all test clean compile-top arithmetic command gpio integration coexist
all: test
$(BUILD):
	mkdir -p $(BUILD)
compile-top: | $(BUILD)
	$(IVERILOG) -g2005 -Wall -s safe_field_tp5_top -o $(BUILD)/tp5_top.vvp $(RTL)
$(BUILD)/%.vvp: tb/%.v $(RTL) | $(BUILD)
	$(IVERILOG) -g2005 -Wall -s $* -o $@ $(RTL) $<
arithmetic: $(BUILD)/tb_arithmetic.vvp
	$(CHECK) --log $(BUILD)/tb_arithmetic.log -- $(VVP) $<
	grep -q 'TEST_RESULT: PASS' $(BUILD)/tb_arithmetic.log
command: $(BUILD)/tb_command_rx.vvp
	$(CHECK) --log $(BUILD)/tb_command_rx.log -- $(VVP) $<
	grep -q 'TEST_RESULT: PASS' $(BUILD)/tb_command_rx.log
gpio: $(BUILD)/tb_gpio_oe.vvp
	$(CHECK) --log $(BUILD)/tb_gpio_oe.log -- $(VVP) $<
	grep -q 'TEST_RESULT: PASS' $(BUILD)/tb_gpio_oe.log
integration: $(BUILD)/tb_tp5_integration.vvp
	$(CHECK) --log $(BUILD)/tb_tp5_integration.log -- $(VVP) $<
	grep -q 'TEST_RESULT: PASS' $(BUILD)/tb_tp5_integration.log
coexist: $(BUILD)/tb_tp5_raw24_coexist.vvp
	$(CHECK) --log $(BUILD)/tb_tp5_raw24_coexist.log -- $(VVP) $<
	grep -q 'TEST_RESULT: PASS' $(BUILD)/tb_tp5_raw24_coexist.log
test: compile-top arithmetic command gpio integration coexist
clean:
	rm -rf $(BUILD)
