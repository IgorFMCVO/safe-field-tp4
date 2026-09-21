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
countmsg: .ascii "COMMANDS_VERIFIED="
.equ countmsg_len, .-countmsg
// cmd, sequence, payload and expected result.  The three numerical commands
// are independently useful FPGA operations; PING establishes link identity.
.balign 4
commands:
    .word 0x01, 0x002a, 0x00000000, 0x54503501
    .word 0x10, 0x002b, 0x40004000, 0x00002000
    .word 0x10, 0x002c, 0x80008000, 0x00008000
    .word 0x11, 0x002d, 0x3e004000, 0x00004200
.equ command_count, 4
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
    LOAD_ADDR x0,t_start
    bl sf_clock_gettime
    cbnz x0,fail_close
    LOAD_ADDR x23,commands
    mov x24,#command_count
command_loop:
    ldr w0,[x23]
    ldr w1,[x23,#4]
    ldr w2,[x23,#8]
    LOAD_ADDR x3,txbuf
    bl sf_build_command
    cmp x0,#11
    b.ne fail_close
    mov x0,x19
    LOAD_ADDR x1,txbuf
    mov x2,#11
    bl sf_write_all
    cbnz x0,fail_close
    // RAW24 can be continuously interleaved on the same UART.  Resynchronize
    // on the TP5 response preamble and discard unrelated complete frames.
    mov x25,#0
    mov x26,#4096
response_scan:
    cmp x25,x26
    b.hs fail_close
    mov x0,x19
    LOAD_ADDR x1,rxbuf
    mov x2,#1
    bl sf_read_exact
    cbnz x0,fail_close
    add x25,x25,#1
    LOAD_ADDR x20,rxbuf
    ldrb w0,[x20]
    cmp w0,#0x5a
    b.ne response_scan
    mov x0,x19
    add x1,x20,#1
    mov x2,#1
    bl sf_read_exact
    cbnz x0,fail_close
    add x25,x25,#1
    ldrb w0,[x20,#1]
    cmp w0,#0xa5
    b.ne response_scan
    mov x0,x19
    add x1,x20,#2
    mov x2,#10
    bl sf_read_exact
    cbnz x0,fail_close
    add x25,x25,#10
    ldr w1,[x23]
    ldr w2,[x23,#4]
    ldr w3,[x23,#12]
    mov x0,x20
    bl sf_validate_response
    cbz x0,response_ok
    // A corrupt or unrelated packet is recoverable; semantic disagreement on
    // our own sequence/result or an FPGA error status is not.
    cmp x0,#-4
    b.eq fail_close
    cmp x0,#-5
    b.eq fail_close
    b response_scan
response_ok:
    add x23,x23,#16
    subs x24,x24,#1
    b.ne command_loop
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
    mov x0,#1
    LOAD_ADDR x1,countmsg
    mov x2,#countmsg_len
    bl sf_write_all
    mov x0,#command_count
    LOAD_ADDR x1,numberbuf
    mov x2,#32
    bl sf_u64_to_ascii
    cbnz x1,fail
    mov x22,x0
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
