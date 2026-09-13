.include "include/syscalls.inc"
.include "include/macros.inc"
.section .rodata
serial_path: .asciz "/dev/serial0"
okmsg: .ascii "SAFE-FIELD TP5 UART round-trip: PASS\n"
.equ okmsg_len, .-okmsg
rttmsg: .ascii "RTT_NS="
.equ rttmsg_len, .-rttmsg
newline: .ascii "\n"
errmsg: .ascii "SAFE-FIELD TP5 UART round-trip: FAIL\n"
.equ errmsg_len, .-errmsg
.text
.global _start
_start:
    // Optional argv[1] selects a device. The test harness uses a PTY.
    // Default remains the physical Pi serial device; no fake hardware mode.
    ldr x0,[sp]
    cmp x0,#2
    b.hi fail
    LOAD_ADDR x0,serial_path
    ldr x1,[sp]
    cmp x1,#2
    b.ne open_device
    ldr x0,[sp,#16]
open_device:
    bl sf_open_rw_noctty
    cmp x0,#0
    b.lt fail
    mov x19,x0
    mov w0,#0x01
    mov w1,#0x002A
    mov w2,#0
    LOAD_ADDR x3,txbuf
    bl sf_build_command
    cmp x0,#11
    b.ne fail_close
    LOAD_ADDR x0,t_start
    bl sf_clock_gettime
    cbnz x0,fail_close
    mov x0,x19
    LOAD_ADDR x1,txbuf
    mov x2,#11
    bl sf_write_all
    cbnz x0,fail_close
    mov x0,x19
    LOAD_ADDR x1,rxbuf
    mov x2,#12
    bl sf_read_exact
    cbnz x0,fail_close
    LOAD_ADDR x0,t_end
    bl sf_clock_gettime
    cbnz x0,fail_close
    // RTT = (end.sec-start.sec)*1e9 + end.nsec-start.nsec.
    LOAD_ADDR x0,t_start
    ldp x1,x2,[x0]
    LOAD_ADDR x0,t_end
    ldp x3,x4,[x0]
    sub x3,x3,x1
    sub x4,x4,x2
    movz x5,#0xCA00
    movk x5,#0x3B9A,lsl #16
    madd x21,x3,x5,x4
    tbnz x21,#63,fail_close
    LOAD_ADDR x20,rxbuf
    ldrb w0,[x20,#0]
    cmp w0,#0x5A
    b.ne fail_close
    ldrb w0,[x20,#1]
    cmp w0,#0xA5
    b.ne fail_close
    ldrb w0,[x20,#2]
    cmp w0,#0x05
    b.ne fail_close
    ldrb w0,[x20,#3]
    cmp w0,#0x01
    b.ne fail_close
    ldrb w0,[x20,#4]
    cbnz w0,fail_close
    ldrb w0,[x20,#5]
    cmp w0,#0x2A
    b.ne fail_close
    add x0,x20,#2
    mov x1,#9
    bl sf_crc8_atm
    ldrb w1,[x20,#11]
    cmp w0,w1
    b.ne fail_close
    // Wire data32 is big-endian. CRC validity is not semantic validity.
    ldr w0,[x20,#6]
    rev w0,w0
    movz w1,#0x3501
    movk w1,#0x5450,lsl #16
    cmp w0,w1
    b.ne fail_close
    ldrb w0,[x20,#10]
    tbnz w0,#7,fail_close
    mov x0,x19
    bl sf_close
    mov x0,x21
    LOAD_ADDR x1,numberbuf
    mov x2,#32
    bl sf_u64_to_ascii
    cbnz x1,fail
    mov x22,x0
    mov x0,#1
    LOAD_ADDR x1,okmsg
    mov x2,#okmsg_len
    bl sf_write_all
    mov x0,#1
    LOAD_ADDR x1,rttmsg
    mov x2,#rttmsg_len
    bl sf_write_all
    mov x0,#1
    LOAD_ADDR x1,numberbuf
    mov x2,x22
    bl sf_write_all
    mov x0,#1
    LOAD_ADDR x1,newline
    mov x2,#1
    bl sf_write_all
    mov x0,#0
    mov x8,#SYS_exit
    svc #0
fail_close:
    mov x0,x19
    bl sf_close
fail:
    mov x0,#2
    LOAD_ADDR x1,errmsg
    mov x2,#errmsg_len
    bl sf_write_all
    mov x0,#1
    mov x8,#SYS_exit
    svc #0
.bss
.balign 16
txbuf: .skip 16
rxbuf: .skip 16
t_start: .skip 16
t_end: .skip 16
numberbuf: .skip 32
.section .note.GNU-stack,"",%progbits
