#define _POSIX_C_SOURCE 200809L
#include "safe_field_arm64.h"

#include <inttypes.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static volatile uint64_t benchmark_sink_u64;
static volatile float benchmark_sink_f32;

static uint64_t ns(void) {
    struct timespec value;
    clock_gettime(CLOCK_MONOTONIC_RAW, &value);
    return (uint64_t)value.tv_sec * 1000000000ULL + (uint64_t)value.tv_nsec;
}

static uint32_t ror32(uint32_t value, unsigned shift) {
    return (value >> shift) | (value << (32U - shift));
}

static uint32_t reference_mix(uint32_t value) {
    uint32_t folded = (value & 0x00ffffffU) ^ (value >> 24);
    return ror32(folded, 8) ^ 0x5aU;
}

static int check_u64(const char *name, uint64_t expected, uint64_t actual) {
    const int pass = expected == actual;
    printf("%-30s expected=%20" PRIu64 " actual=%20" PRIu64 " %s\n",
           name, expected, actual, pass ? "PASS" : "FAIL");
    return !pass;
}

int main(int argc, char **argv) {
    const size_t n = 65536;
    const unsigned repeats = argc > 1 ? (unsigned)strtoul(argv[1], NULL, 10) : 400;
    int errors = 0;
    uint64_t out[2];

    puts("SAFE-FIELD TP4 AArch64 expected x actual");
    sf_add128(UINT64_MAX, UINT64_MAX, 1, 0, out);
    errors += check_u64("add128 overflow low", 0, out[0]);
    errors += check_u64("add128 overflow high", 0, out[1]);
    sf_add128(0x0123456789abcdefULL, 0x1111111111111111ULL,
              0xfedcba9876543210ULL, 0x2222222222222222ULL, out);
    errors += check_u64("add128 vector low", UINT64_MAX, out[0]);
    errors += check_u64("add128 vector high", 0x3333333333333333ULL, out[1]);

    const int64_t integer_value = -123456789;
    const double converted = sf_i64_to_double(integer_value);
    const int conversion_pass = converted == (double)integer_value;
    printf("%-30s expected=%.1f actual=%.1f %s\n", "SCVTF integer->double",
           (double)integer_value, converted, conversion_pass ? "PASS" : "FAIL");
    errors += !conversion_pass;

    errors += check_u64("lookup ACTIVE", 1, sf_lookup_state(1));
    errors += check_u64("lookup invalid", 255, sf_lookup_state(9));
    errors += check_u64("mask/shift/rotate", reference_mix(0xa5123456U),
                        sf_protocol_mix(0xa5123456U));

    int16_t *samples = aligned_alloc(16, n * sizeof(*samples));
    float *float_in = aligned_alloc(16, n * sizeof(*float_in));
    float *scalar_out = aligned_alloc(16, n * sizeof(*scalar_out));
    float *neon_out = aligned_alloc(16, n * sizeof(*neon_out));
    if (!samples || !float_in || !scalar_out || !neon_out) {
        fputs("allocation failure\n", stderr);
        return 2;
    }
    for (size_t i = 0; i < n; ++i) {
        samples[i] = (int16_t)(((i * 73U + 19U) % 2001U) - 1000);
        float_in[i] = (float)samples[i] / 32768.0f;
    }

    const uint64_t scalar_energy = sf_energy_scalar_i16(samples, n);
    const uint64_t neon_energy = sf_energy_neon_i16(samples, n);
    errors += check_u64("NEON integer exact energy", scalar_energy, neon_energy);

    sf_scale_scalar_f32(float_in, scalar_out, n, 0.625f);
    sf_scale_neon_f32(float_in, neon_out, n, 0.625f);
    float max_error = 0.0f;
    for (size_t i = 0; i < n; ++i) {
        const float error = fabsf(scalar_out[i] - neon_out[i]);
        if (error > max_error) max_error = error;
    }
    const int float_pass = max_error <= 1.0e-7f;
    printf("%-30s tolerance=1e-7 max_error=%g %s\n", "NEON float scale",
           (double)max_error, float_pass ? "PASS" : "FAIL");
    errors += !float_pass;

    uint64_t start = ns();
    for (unsigned r = 0; r < repeats; ++r)
        benchmark_sink_u64 ^= sf_energy_scalar_i16(samples, n);
    const uint64_t scalar_int_ns = ns() - start;
    start = ns();
    for (unsigned r = 0; r < repeats; ++r)
        benchmark_sink_u64 ^= sf_energy_neon_i16(samples, n);
    const uint64_t neon_int_ns = ns() - start;

    start = ns();
    for (unsigned r = 0; r < repeats; ++r) {
        sf_scale_scalar_f32(float_in, scalar_out, n, 0.625f);
        benchmark_sink_f32 += scalar_out[r % n];
    }
    const uint64_t scalar_float_ns = ns() - start;
    start = ns();
    for (unsigned r = 0; r < repeats; ++r) {
        sf_scale_neon_f32(float_in, neon_out, n, 0.625f);
        benchmark_sink_f32 += neon_out[r % n];
    }
    const uint64_t neon_float_ns = ns() - start;

    printf("BENCHMARK elements=%zu repeats=%u\n", n, repeats);
    printf("NEON_INT scalar_ns=%" PRIu64 " neon_ns=%" PRIu64 " speedup=%.6f lanes=8\n",
           scalar_int_ns, neon_int_ns, (double)scalar_int_ns / (double)neon_int_ns);
    printf("NEON_FLOAT scalar_ns=%" PRIu64 " neon_ns=%" PRIu64 " speedup=%.6f lanes=4\n",
           scalar_float_ns, neon_float_ns, (double)scalar_float_ns / (double)neon_float_ns);
    printf("TEST_RESULT: %s errors=%d\n", errors ? "FAIL" : "PASS", errors);

    free(neon_out); free(scalar_out); free(float_in); free(samples);
    return errors ? 1 : 0;
}
