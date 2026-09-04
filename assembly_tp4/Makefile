CC ?= gcc
CFLAGS ?= -O3 -Wall -Wextra -Werror -std=c11

.PHONY: all test disassembly clean

all: safe_field_arm64_test

safe_field_arm64_test: harness.o safe_field_arm64.o
	$(CC) $(CFLAGS) -o $@ $^ -lm

harness.o: harness.c safe_field_arm64.h
	$(CC) $(CFLAGS) -c -o $@ harness.c

safe_field_arm64.o: safe_field_arm64.S
	$(CC) $(CFLAGS) -c -o $@ safe_field_arm64.S

test: safe_field_arm64_test
	./safe_field_arm64_test 400

disassembly: safe_field_arm64_test
	objdump -d -S safe_field_arm64_test > safe_field_arm64_test.objdump.txt

clean:
	rm -f *.o safe_field_arm64_test safe_field_arm64_test.objdump.txt
