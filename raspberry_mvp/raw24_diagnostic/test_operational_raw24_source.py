from __future__ import annotations

import struct
import unittest

from .operational_raw24_source import SharedRaw24TP5Parser
from .safe_field_raw24_protocol import Raw24Frame, encode_frame


def raw_frame(seq: int, samples: tuple[int, ...] | None = None) -> bytes:
    pcm = samples or tuple(range(-8, 8))
    return encode_frame(
        Raw24Frame(
            seq=seq,
            first_source_sample_counter=seq * 32,
            stride=2,
            flags=0,
            raw24_samples=tuple(sample << 5 for sample in pcm),
            pcm16_samples=pcm,
        )
    )


def tp5_reply(sequence: int = 7) -> bytes:
    # 5A A5 / protocol v05 / reply type 01 / BE sequence / payload / flags / CRC-8.
    body = bytes((5, 1, (sequence >> 8) & 0xFF, sequence & 0xFF, 0x54, 0x50, 0x35, 1, 0))
    value = 0
    for byte in body:
        value ^= byte
        for _ in range(8):
            value = ((value << 1) ^ 0x07) & 0xFF if value & 0x80 else (value << 1) & 0xFF
    return b"\x5A\xA5" + body + bytes((value,))


class SharedRaw24TP5ParserTests(unittest.TestCase):
    def test_fragmented_frame_preserves_embedded_pcm16_exactly(self):
        parser = SharedRaw24TP5Parser()
        packet = raw_frame(1)
        self.assertEqual(parser.feed(packet[:19]), [])
        result = parser.feed(packet[19:])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].pcm16_samples, tuple(range(-8, 8)))
        self.assertEqual(struct.unpack("<16h", struct.pack("<16h", *result[0].pcm16_samples)), tuple(range(-8, 8)))

    def test_consecutive_frames_are_not_merged(self):
        parser = SharedRaw24TP5Parser()
        result = parser.feed(raw_frame(3) + raw_frame(4, tuple(range(16))))
        self.assertEqual([frame.seq for frame in result], [3, 4])
        self.assertEqual(result[1].pcm16_samples, tuple(range(16)))
        self.assertEqual(parser.valid_frames, 2)

    def test_invalid_raw_crc_is_rejected_before_next_valid_frame(self):
        parser = SharedRaw24TP5Parser()
        corrupt = bytearray(raw_frame(8)); corrupt[-1] ^= 0x80
        result = parser.feed(raw_frame(7) + bytes(corrupt) + raw_frame(9))
        self.assertEqual([frame.seq for frame in result], [7, 9])
        self.assertEqual(parser.crc_errors, 1)

    def test_tp5_reply_is_counted_but_never_emitted_as_audio(self):
        parser = SharedRaw24TP5Parser()
        result = parser.feed(raw_frame(10) + tp5_reply(11) + raw_frame(12))
        self.assertEqual([frame.seq for frame in result], [10, 12])
        self.assertEqual(parser.tp5_response_frames, 1)
        self.assertEqual(parser.tp5_response_crc_errors, 0)
        self.assertEqual(parser.crc_errors, 0)


if __name__ == "__main__":
    unittest.main()
