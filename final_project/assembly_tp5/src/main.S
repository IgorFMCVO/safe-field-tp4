.include "include/syscalls.inc"
.include "include/macros.inc"
.section .rodata
banner: .ascii "SAFE-FIELD TP5 ARM64 stand-alone: PASS\n"
.equ banner_len, .-banner
label1: .ascii "ascii_to_u64(12345)="
.equ label1_len, .-label1
inputnum: .ascii "12345"
newline: .ascii "\n"
.text
.global _start
_start:
    LOAD_ADDR x0,inputnum
    mov x1,#5
    bl sf_ascii_to_u64
    cbnz x1,fail
    mov x19,x0
    mov x0,x19
    LOAD_ADDR x1,outbuf
    mov x2,#32
    bl sf_u64_to_ascii
    cbnz x1,fail
    mov x20,x0
    mov w0,#0x01
    mov w1,#0x002A
    mov w2,#0
    LOAD_ADDR x3,framebuf
    bl sf_build_command
    cmp x0,#11
    b.ne fail
    mov x0,#1
    LOAD_ADDR x1,banner
    mov x2,#banner_len
    bl sf_write_all
    mov x0,#1
    LOAD_ADDR x1,label1
    mov x2,#label1_len
    bl sf_write_all
    mov x0,#1
    LOAD_ADDR x1,outbuf
    mov x2,x20
    bl sf_write_all
    mov x0,#1
    LOAD_ADDR x1,newline
    mov x2,#1
    bl sf_write_all
    mov x0,#0
    mov x8,#SYS_exit
    svc #0
fail:
    mov x0,#1
    mov x8,#SYS_exit
    svc #0

.bss
.balign 16
outbuf: .skip 32
framebuf: .skip 16
