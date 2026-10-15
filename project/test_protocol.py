import struct
import unittest
from lite3 import decode_packet, encode_simple


class ProtocolTests(unittest.TestCase):
    def test_heartbeat_wire_bytes(self):
        self.assertEqual(encode_simple(0x21040001).hex(), "010004210000000000000000")

    def test_signed_parameter(self):
        self.assertEqual(encode_simple(1, -1)[4:8], bytes.fromhex("ffffffff"))
        self.assertEqual(decode_packet(bytes.fromhex("01000000ffffffff00000000"))["value"], -1)

    def test_manual_appendix_joint_sample(self):
        packet = bytes.fromhex(
            "0209000060000000010000002efd3ccf47e4e1bf"
            "f1304992f49ee7bfc3d7eefe8567f13f9ae4b66d6583f1bf"
            "24d8f33c3d00f13f8c16222a0b1f0140e8baaaaa3803ef3f"
            "d009000060bdd2bfdb0433531150e73f7d0b000072f0e53f"
            "0a3d0cc3f071e73fc3d7eefe7b52f93f")
        result = decode_packet(packet)
        self.assertEqual(len(result["joints"]), 12)
        self.assertAlmostEqual(result["joints"][0], -0.5591162726995316)
        self.assertAlmostEqual(result["joints"][-1], 1.5826377828902742)

    def test_bad_packets(self):
        for packet in (b"", b"123", struct.pack("<III", 1, 8, 1),
                       struct.pack("<III", 1, 0, 2),
                       struct.pack("<III", 1, 0, 0) + b"x",
                       struct.pack("<III", 0x902, 8, 1) + bytes(8)):
            with self.subTest(packet=packet), self.assertRaises(ValueError):
                decode_packet(packet)

    def test_unknown_complex_preserved(self):
        result = decode_packet(struct.pack("<III", 0x901, 3, 1) + b"abc")
        self.assertEqual(result["payload_hex"], "616263")


if __name__ == "__main__":
    unittest.main()
