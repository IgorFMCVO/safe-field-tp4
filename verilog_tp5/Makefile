IVERILOG ?= iverilog
VVP ?= vvp
BUILD := build
RTL = rtl/i2s_clock_gen.v rtl/i2s_rx_24.v rtl/audio_energy_detector.v \
      rtl/uart_rx_byte.v rtl/uart_tx_byte.v rtl/sf_command_rx.v \
      rtl/sf_telemetry_tx.v rtl/sf_fixed_q15_mac.v rtl/sf_fp16_mul.v \
      rtl/sf_gpio_oe.v rtl/safe_field_tp5_top.v

.PHONY: all test clean compile-top arithmetic command gpio integration
all: test

$(BUILD):
	mkdir -p $(BUILD)

compile-top: $(BUILD)
	$(IVERILOG) -g2005 -s safe_field_tp5_top -o $(BUILD)/tp5_top.vvp $(RTL)

arithmetic: $(BUILD)
	$(IVERILOG) -g2005 -s tb_arithmetic -o $(BUILD)/tb_arithmetic.vvp $(RTL) tb/tb_arithmetic.v
	$(VVP) $(BUILD)/tb_arithmetic.vvp | tee $(BUILD)/tb_arithmetic.log
	grep -q "TEST_RESULT: PASS" $(BUILD)/tb_arithmetic.log

command: $(BUILD)
	$(IVERILOG) -g2005 -s tb_command_rx -o $(BUILD)/tb_command_rx.vvp $(RTL) tb/tb_command_rx.v
	$(VVP) $(BUILD)/tb_command_rx.vvp | tee $(BUILD)/tb_command_rx.log
	grep -q "TEST_RESULT: PASS" $(BUILD)/tb_command_rx.log

gpio: $(BUILD)
	$(IVERILOG) -g2005 -s tb_gpio_oe -o $(BUILD)/tb_gpio_oe.vvp $(RTL) tb/tb_gpio_oe.v
	$(VVP) $(BUILD)/tb_gpio_oe.vvp | tee $(BUILD)/tb_gpio_oe.log
	grep -q "TEST_RESULT: PASS" $(BUILD)/tb_gpio_oe.log

integration: $(BUILD)
	$(IVERILOG) -g2005 -s tb_tp5_integration -o $(BUILD)/tb_tp5_integration.vvp $(RTL) tb/tb_tp5_integration.v
	$(VVP) $(BUILD)/tb_tp5_integration.vvp | tee $(BUILD)/tb_tp5_integration.log
	grep -q "TEST_RESULT: PASS" $(BUILD)/tb_tp5_integration.log

test: compile-top arithmetic command gpio integration

clean:
	rm -rf $(BUILD)
