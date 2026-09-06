"""Bit-exact checks for the UART-PCM16 to evidence-WAV amplitude boundary.

These tests deliberately start at the documented UART packet contract.  They
do not model an acoustic source or claim hardware evidence; their purpose is to
prove that the Raspberry decoder and raw evidence writer apply no hidden gain,
normalization, DC removal, clipping, or endian conversion to accepted PCM16.
"""

from __future__ import annotations

from array import array
import hashlib
import io
import math
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
import wave

from mvp.operational_intelligence.audio import PCMFormat, SegmenterConfig
from mvp.operational_intelligence.core import OperationalIntelligenceCore
from raspberry_mvp.pcm_stream.safe_field_pcm_protocol import PCMFrame, encode_frame
from raspberry_mvp.pcm_stream.safe_field_pcm_receiver import (
    SerialPCMSource,
    capture_stream,
)


def pcm16_le(values: list[int]) -> bytes:
    packed = array("h", values)
    if sys.byteorder == "big":
        packed.byteswap()
    return packed.tobytes()


def read_wav_pcm(path: Path) -> tuple[tuple[int, int, int], bytes, list[int]]:
    with wave.open(str(path), "rb") as stream:
        header = (stream.getnchannels(), stream.getsampwidth(), stream.getframerate())
        payload = stream.readframes(stream.getnframes())
    decoded = array("h")
    decoded.frombytes(payload)
    if sys.byteorder == "big":
        decoded.byteswap()
    return header, payload, list(decoded)


class FragmentedBytes:
    """A deterministic serial-like reader that splits every protocol field."""

    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.offset = 0
        self.read_index = 0
        self.widths = (1, 2, 3, 5, 7, 11, 13, 17, 29, 31, 47, 61, 73)

    def read(self, maximum: int) -> bytes:
        if self.offset >= len(self.payload):
            return b""
        width = min(maximum, self.widths[self.read_index % len(self.widths)])
        self.read_index += 1
        end = min(len(self.payload), self.offset + width)
        result = self.payload[self.offset : end]
        self.offset = end
        return result


class PCMAmplitudeIdentityTests(unittest.TestCase):
    def test_constant_dc_level_is_not_centered_or_rescaled_in_wav(self):
        expected = [1_234] * 32
        packet = encode_frame(PCMFrame(0, 0, 0, tuple(expected)))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "constant_dc.wav"
            report = capture_stream(io.BytesIO(packet), output, None)
            _header, payload, actual = read_wav_pcm(output)

        self.assertEqual(actual, expected)
        self.assertEqual(payload, struct.pack("<32h", *expected))
        self.assertEqual(sum(actual) / len(actual), 1_234.0)
        self.assertEqual(
            math.sqrt(sum(value * value for value in actual) / len(actual)),
            1_234.0,
        )
        self.assertTrue(report["acceptance_pass"])

    def test_every_pcm16_code_survives_packet_parser_and_wav_writer_bit_exactly(self):
        expected = list(range(-32_768, 32_768))
        packets = []
        for packet_index in range(0, len(expected), 32):
            block = tuple(expected[packet_index : packet_index + 32])
            packets.append(
                encode_frame(
                    PCMFrame(
                        seq=packet_index // 32,
                        first_sample_counter=packet_index,
                        flags=0,
                        samples=block,
                    )
                )
            )

        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "all_pcm16_codes.wav"
            report = capture_stream(FragmentedBytes(b"".join(packets)), output, None)
            header, wav_payload, actual = read_wav_pcm(output)

        expected_payload = pcm16_le(expected)
        self.assertEqual(header, (1, 2, 42_188))
        self.assertEqual(actual, expected)
        self.assertEqual(wav_payload, expected_payload)
        self.assertEqual(
            hashlib.sha256(wav_payload).digest(),
            hashlib.sha256(expected_payload).digest(),
        )
        self.assertEqual(report["samples_written"], 65_536)
        self.assertEqual(report["valid_frames"], 2_048)
        self.assertEqual(report["crc_errors"], 0)
        self.assertEqual(report["format_errors"], 0)
        self.assertEqual(report["sequence_losses"], 0)
        self.assertEqual(report["sample_losses"], 0)
        self.assertTrue(report["acceptance_pass"])

        # Independent amplitude-domain invariants.  No centering is applied:
        # the signed PCM16 code domain has the expected exact mean of -0.5.
        self.assertEqual(min(actual), -32_768)
        self.assertEqual(max(actual), 32_767)
        self.assertEqual(sum(actual) / len(actual), -0.5)
        self.assertEqual(
            math.sqrt(sum(value * value for value in actual) / len(actual)),
            math.sqrt(sum(value * value for value in expected) / len(expected)),
        )

    def test_serial_decoder_to_operational_raw_wav_has_no_amplitude_transform(self):
        samples = [
            -32_768,
            -32_767,
            -30_000,
            -16_384,
            -8_193,
            -8_192,
            -257,
            -256,
            -255,
            -2,
            -1,
            0,
            1,
            2,
            31,
            32,
            33,
            127,
            128,
            255,
            256,
            257,
            8_191,
            8_192,
            8_193,
            16_383,
            16_384,
            30_000,
            32_765,
            32_766,
            32_767,
            12_345,
        ]
        samples += [-value if value != -32_768 else 32_767 for value in samples]
        self.assertEqual(len(samples), 64)
        payload = b"".join(
            encode_frame(
                PCMFrame(
                    seq=index,
                    first_sample_counter=index * 32,
                    flags=0,
                    samples=tuple(samples[index * 32 : (index + 1) * 32]),
                )
            )
            for index in range(2)
        )

        class FragmentedSerial:
            def __init__(self, *_args, **_kwargs) -> None:
                self.reader = FragmentedBytes(payload)
                self.closed = False

            def read(self, maximum: int) -> bytes:
                data = self.reader.read(maximum)
                if not data:
                    time.sleep(0.001)
                return data

            def close(self) -> None:
                self.closed = True

        with tempfile.TemporaryDirectory() as directory:
            sessions = Path(directory) / "sessions"
            source = SerialPCMSource("TEST_PORT", serial_factory=FragmentedSerial)
            core = OperationalIntelligenceCore(
                sessions,
                pcm=PCMFormat(sample_rate=42_188, channels=1, sample_width=2),
                segmentation=SegmenterConfig(speech_rms_threshold=32_767),
                pcm_source=source,
            )
            core.start("PCM_AMPLITUDE_IDENTITY")
            deadline = time.monotonic() + 2.0
            while (
                core.status().get("pcm_source", {}).get("samples_received", 0) < len(samples)
                and time.monotonic() < deadline
            ):
                time.sleep(0.005)
            stopped = core.stop(2.0)
            raw_path = sessions / "PCM_AMPLITUDE_IDENTITY" / "audio" / "raw.wav"
            processed_path = (
                sessions / "PCM_AMPLITUDE_IDENTITY" / "audio" / "processed.wav"
            )
            raw_header, raw_payload, raw_values = read_wav_pcm(raw_path)
            processed_header, processed_payload, processed_values = read_wav_pcm(
                processed_path
            )

        expected_payload = struct.pack("<64h", *samples)
        self.assertEqual(raw_header, (1, 2, 42_188))
        self.assertEqual(processed_header, raw_header)
        self.assertEqual(raw_values, samples)
        self.assertEqual(processed_values, samples)
        self.assertEqual(raw_payload, expected_payload)
        self.assertEqual(processed_payload, expected_payload)
        self.assertEqual(stopped["capture"]["frames"], len(samples))
        self.assertEqual(stopped["pcm_source"]["samples_received"], len(samples))
        self.assertEqual(stopped["pcm_source"]["valid_frames"], 2)
        self.assertEqual(stopped["pcm_source"]["crc_errors"], 0)
        self.assertEqual(stopped["pcm_source"]["sequence_losses"], 0)
        self.assertEqual(stopped["pcm_source"]["sample_losses"], 0)


if __name__ == "__main__":
    unittest.main()
