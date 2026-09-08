CROSS ?= aarch64-linux-gnu-
AS := $(CROSS)as
AR := $(CROSS)ar
LD := $(CROSS)ld
OBJDUMP := $(CROSS)objdump
QEMU ?= qemu-aarch64
BUILD := build
LIBOBJ := $(BUILD)/io_syscalls.o $(BUILD)/buffer.o $(BUILD)/parse.o $(BUILD)/arithmetic.o $(BUILD)/protocol.o

.PHONY: all clean test disasm
all: $(BUILD)/tp5_demo $(BUILD)/tp5_uart_demo $(BUILD)/libsafe_field_tp5.a

$(BUILD):
	mkdir -p $(BUILD)

$(BUILD)/%.o: src/%.S | $(BUILD)
	$(AS) -I . -o $@ $<

$(BUILD)/main.o: src/main.S | $(BUILD)
	$(AS) -I . -o $@ $<

$(BUILD)/uart_client.o: src/uart_client.S | $(BUILD)
	$(AS) -I . -o $@ $<

$(BUILD)/libsafe_field_tp5.a: $(LIBOBJ)
	$(AR) rcs $@ $^

$(BUILD)/tp5_demo: $(BUILD)/main.o $(BUILD)/libsafe_field_tp5.a
	$(LD) -static -e _start -o $@ $(BUILD)/main.o $(BUILD)/libsafe_field_tp5.a

$(BUILD)/tp5_uart_demo: $(BUILD)/uart_client.o $(BUILD)/libsafe_field_tp5.a
	$(LD) -static -e _start -o $@ $(BUILD)/uart_client.o $(BUILD)/libsafe_field_tp5.a

test: all
	$(QEMU) $(BUILD)/tp5_demo | tee $(BUILD)/qemu_run.log
	grep -q "stand-alone: PASS" $(BUILD)/qemu_run.log
	python3 tests/reference_tests.py

disasm: all
	$(OBJDUMP) -d $(BUILD)/tp5_demo > $(BUILD)/tp5_demo.objdump.txt
	$(OBJDUMP) -d $(BUILD)/tp5_uart_demo > $(BUILD)/tp5_uart_demo.objdump.txt

clean:
	rm -rf $(BUILD)
