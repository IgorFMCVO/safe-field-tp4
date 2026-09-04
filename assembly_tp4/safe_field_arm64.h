#ifndef SAFE_FIELD_ARM64_H
#define SAFE_FIELD_ARM64_H

#include <stddef.h>
#include <stdint.h>

void sf_add128(uint64_t a_lo, uint64_t a_hi, uint64_t b_lo, uint64_t b_hi, uint64_t out[2]);
double sf_i64_to_double(int64_t value);
uint32_t sf_lookup_state(uint32_t index);
uint32_t sf_protocol_mix(uint32_t value);
uint64_t sf_energy_scalar_i16(const int16_t *samples, size_t count);
uint64_t sf_energy_neon_i16(const int16_t *samples, size_t count);
void sf_scale_scalar_f32(const float *input, float *output, size_t count, float scale);
void sf_scale_neon_f32(const float *input, float *output, size_t count, float scale);

#endif
