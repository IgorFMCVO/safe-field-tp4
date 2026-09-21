CROSS ?= aarch64-linux-gnu-
AS := $(CROSS)as
AR := $(CROSS)ar
LD := $(CROSS)ld
CC := $(CROSS)gcc
OBJDUMP := $(CROSS)objdump
HOST := $(shell uname -s)/$(shell uname -m)
RUNNER ?= $(if $(filter Linux/aarch64 Linux/arm64,$(HOST)),,qemu-aarch64)
PYTHON ?= python3
BUILD := build
LIBOBJ := $(addprefix $(BUILD)/,io_syscalls.o buffer.o parse.o arithmetic.o protocol.o)
INCLUDES := $(wildcard include/*.inc)
CHECK := $(PYTHON) ../scripts/run_checked.py --timeout 30
.PHONY: all clean test test-offline disasm
all: $(BUILD)/tp5_demo $(BUILD)/tp5_uart_demo $(BUILD)/libsafe_field_tp5.a
$(BUILD):
	mkdir -p $(BUILD)
$(BUILD)/%.o: src/%.S $(INCLUDES) | $(BUILD)
	$(AS) -g -I . -o $@ $<
$(BUILD)/libsafe_field_tp5.a: $(LIBOBJ)
	$(AR) rcs $@ $^
$(BUILD)/tp5_demo: $(BUILD)/main.o $(BUILD)/libsafe_field_tp5.a
	$(LD) -static -z noexecstack -e _start -o $@ $^
$(BUILD)/tp5_uart_demo: $(BUILD)/uart_client.o $(BUILD)/libsafe_field_tp5.a
	$(LD) -static -z noexecstack -e _start -o $@ $^
$(BUILD)/abi_tests: tests/abi_tests.c $(BUILD)/libsafe_field_tp5.a
	$(CC) -O2 -Wall -Wextra -static -Wl,-z,noexecstack -o $@ $^
test: test-offline
test-offline: all $(BUILD)/abi_tests
	$(CHECK) --log $(BUILD)/qemu_run.log -- $(RUNNER) $(BUILD)/tp5_demo
	grep -q 'stand-alone: PASS' $(BUILD)/qemu_run.log
	$(CHECK) --log $(BUILD)/assembly_abi_tests.log -- $(RUNNER) $(BUILD)/abi_tests
	$(CHECK) --log $(BUILD)/uart_client_pty.log -- $(PYTHON) tests/uart_client_pty.py --runner '$(RUNNER)'
	$(PYTHON) tests/reference_tests.py
disasm: all
	$(OBJDUMP) -d $(BUILD)/tp5_demo > $(BUILD)/tp5_demo.objdump.txt
	$(OBJDUMP) -d $(BUILD)/tp5_uart_demo > $(BUILD)/tp5_uart_demo.objdump.txt
	$(AR) t $(BUILD)/libsafe_field_tp5.a > $(BUILD)/library_members.txt
clean:
	rm -rf $(BUILD)
