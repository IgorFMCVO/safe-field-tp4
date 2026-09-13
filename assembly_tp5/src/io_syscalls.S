.include "include/syscalls.inc"
.include "include/macros.inc"
.text
.global sf_write_all
.type sf_write_all,%function
// x0=fd,x1=buffer,x2=len -> 0 complete or negative Linux errno.
// EINTR retries. A zero-byte write with data pending is -EIO.
sf_write_all:
    PUSH2 x19,x20
    mov x19,x0
    mov x20,x1
1:  cbz x2,3f
    mov x0,x19
    mov x1,x20
    mov x8,#SYS_write
    svc #0
    cmn x0,#4
    b.eq 1b
    cmp x0,#0
    b.lt 2f
    b.eq 4f
    add x20,x20,x0
    sub x2,x2,x0
    b 1b
4:  mov x0,#-5
2:  POP2 x19,x20
    ret
3:  mov x0,#0
    POP2 x19,x20
    ret
.global sf_clock_gettime
.type sf_clock_gettime,%function
// x0=timespec pointer -> syscall status; CLOCK_MONOTONIC.
sf_clock_gettime:
    mov x1,x0
    mov x0,#CLOCK_MONOTONIC
    mov x8,#SYS_clock_gettime
    svc #0
    ret
.global sf_read_exact
.type sf_read_exact,%function
// x0=fd,x1=buffer,x2=len -> 0 complete, -ENODATA on premature EOF.
// Partial data may exist on error: discard the frame. EINTR retries.
// Blocking: UART caller must configure device timeout or a watchdog.
sf_read_exact:
    PUSH2 x19,x20
    mov x19,x0
    mov x20,x1
5:  cbz x2,7f
    mov x0,x19
    mov x1,x20
    mov x8,#SYS_read
    svc #0
    cmn x0,#4
    b.eq 5b
    cmp x0,#0
    b.lt 6f
    b.eq 8f
    add x20,x20,x0
    sub x2,x2,x0
    b 5b
8:  mov x0,#-61
6:  POP2 x19,x20
    ret
7:  mov x0,#0
    POP2 x19,x20
    ret
.global sf_open_rw_noctty
.type sf_open_rw_noctty,%function
// x0=path -> fd/error. Serial configuration is caller-owned.
sf_open_rw_noctty:
    mov x1,x0
    mov x0,#AT_FDCWD
    mov x2,#0x102
    mov x3,#0
    mov x8,#SYS_openat
    svc #0
    ret
.global sf_close
.type sf_close,%function
sf_close:
    mov x8,#SYS_close
    svc #0
    ret
.section .note.GNU-stack,"",%progbits
