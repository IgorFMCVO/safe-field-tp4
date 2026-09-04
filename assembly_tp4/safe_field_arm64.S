// SAFE-FIELD TP4 — AArch64 scalar, bitwise and NEON routines.
// Tested on the real Raspberry Pi 4; AAPCS64 calling convention.

.text
.align 2

.global sf_add128
.type sf_add128, %function
// void sf_add128(a_lo, a_hi, b_lo, b_hi, uint64_t out[2])
sf_add128:
    adds    x5, x0, x2
    adc     x6, x1, x3
    stp     x5, x6, [x4]
    ret
.size sf_add128, .-sf_add128

.global sf_i64_to_double
.type sf_i64_to_double, %function
// double sf_i64_to_double(int64_t value)
sf_i64_to_double:
    scvtf   d0, x0
    ret
.size sf_i64_to_double, .-sf_i64_to_double

.global sf_lookup_state
.type sf_lookup_state, %function
// uint32_t sf_lookup_state(uint32_t index), invalid -> ATTENTION (0xff)
sf_lookup_state:
    cmp     w0, #4
    b.hs    .Llookup_invalid
    adrp    x1, sf_state_lut
    add     x1, x1, :lo12:sf_state_lut
    ldr     w0, [x1, w0, uxtw #2]
    ret
.Llookup_invalid:
    mov     w0, #0xff
    ret
.size sf_lookup_state, .-sf_lookup_state

.global sf_protocol_mix
.type sf_protocol_mix, %function
// Mask 24-bit energy, fold the flag byte, rotate right and apply sync mask.
sf_protocol_mix:
    and     w1, w0, #0x00ffffff
    lsr     w2, w0, #24
    eor     w1, w1, w2
    ror     w1, w1, #8
    mov     w2, #0x5a
    eor     w0, w1, w2
    ret
.size sf_protocol_mix, .-sf_protocol_mix

.global sf_energy_scalar_i16
.type sf_energy_scalar_i16, %function
// uint64_t sf_energy_scalar_i16(const int16_t *samples, size_t count)
sf_energy_scalar_i16:
    mov     x3, #0
    cbz     x1, .Lenergy_scalar_done
.Lenergy_scalar_loop:
    ldrsh   w4, [x0], #2
    smull   x4, w4, w4
    add     x3, x3, x4
    subs    x1, x1, #1
    b.ne    .Lenergy_scalar_loop
.Lenergy_scalar_done:
    mov     x0, x3
    ret
.size sf_energy_scalar_i16, .-sf_energy_scalar_i16

.global sf_energy_neon_i16
.type sf_energy_neon_i16, %function
// Eight signed 16-bit samples per NEON iteration, exact 64-bit accumulation.
sf_energy_neon_i16:
    movi    v4.2d, #0
    mov     x3, #0
    cmp     x1, #8
    b.lo    .Lenergy_neon_tail
.Lenergy_neon_loop:
    ldr     q0, [x0], #16
    smull   v1.4s, v0.4h, v0.4h
    smull2  v2.4s, v0.8h, v0.8h
    uadalp  v4.2d, v1.4s
    uadalp  v4.2d, v2.4s
    sub     x1, x1, #8
    cmp     x1, #8
    b.hs    .Lenergy_neon_loop
    addp    d4, v4.2d
    fmov    x3, d4
.Lenergy_neon_tail:
    cbz     x1, .Lenergy_neon_done
.Lenergy_neon_tail_loop:
    ldrsh   w4, [x0], #2
    smull   x4, w4, w4
    add     x3, x3, x4
    subs    x1, x1, #1
    b.ne    .Lenergy_neon_tail_loop
.Lenergy_neon_done:
    mov     x0, x3
    ret
.size sf_energy_neon_i16, .-sf_energy_neon_i16

.global sf_scale_scalar_f32
.type sf_scale_scalar_f32, %function
// void sf_scale_scalar_f32(in, out, count, float scale)
sf_scale_scalar_f32:
    cbz     x2, .Lscale_scalar_done
.Lscale_scalar_loop:
    ldr     s1, [x0], #4
    fmul    s1, s1, s0
    str     s1, [x1], #4
    subs    x2, x2, #1
    b.ne    .Lscale_scalar_loop
.Lscale_scalar_done:
    ret
.size sf_scale_scalar_f32, .-sf_scale_scalar_f32

.global sf_scale_neon_f32
.type sf_scale_neon_f32, %function
// Four IEEE-754 single-precision values per NEON iteration.
sf_scale_neon_f32:
    dup     v3.4s, v0.s[0]
    cmp     x2, #4
    b.lo    .Lscale_neon_tail
.Lscale_neon_loop:
    ldr     q1, [x0], #16
    fmul    v1.4s, v1.4s, v3.4s
    str     q1, [x1], #16
    sub     x2, x2, #4
    cmp     x2, #4
    b.hs    .Lscale_neon_loop
.Lscale_neon_tail:
    cbz     x2, .Lscale_neon_done
.Lscale_neon_tail_loop:
    ldr     s1, [x0], #4
    fmul    s1, s1, s0
    str     s1, [x1], #4
    subs    x2, x2, #1
    b.ne    .Lscale_neon_tail_loop
.Lscale_neon_done:
    ret
.size sf_scale_neon_f32, .-sf_scale_neon_f32

.section .rodata
.align 4
sf_state_lut:
    .word 0x00000000 // QUIET
    .word 0x00000001 // ACTIVE
    .word 0x00000010 // CAMERA_NOT_CONNECTED
    .word 0x000000ff // ATTENTION

.section .note.GNU-stack,"",%progbits
