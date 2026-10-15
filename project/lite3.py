"""Lite 3 UDP protocol tools. Based on local interface manual V1.0.7-0."""
import argparse
import ipaddress
import json
import socket
import struct
import time

HEADER = struct.Struct("<III")
COMMANDS = {
    "heartbeat": 0x21040001,
    "stand-sit-toggle": 0x21010202,
    "soft-estop": 0x21020C0E,
    "pose-mode": 0x21010D05,
    "move-mode": 0x21010D06,
}


def encode_simple(code, value=0):
    if not 0 <= code <= 0xFFFFFFFF:
        raise ValueError("Command code must fit uint32")
    if not -(2**31) <= value < 2**31:
        raise ValueError("Value must fit int32")
    return HEADER.pack(code, value & 0xFFFFFFFF, 0)


def decode_packet(packet):
    if len(packet) < HEADER.size:
        raise ValueError("Truncated header")
    code, field, kind = HEADER.unpack_from(packet)
    result = {"code": f"0x{code:08X}", "type": kind}
    payload = packet[HEADER.size:]
    if kind == 0:
        if payload:
            raise ValueError("Simple command must be exactly 12 bytes")
        result["value"] = field if field < 2**31 else field - 2**32
    elif kind == 1:
        if len(payload) != field:
            raise ValueError("Payload length differs from header")
        if code in (0x0902, 0x0903):
            if len(payload) != 96:
                raise ValueError("Joint telemetry must contain 12 doubles")
            result["joints"] = struct.unpack("<12d", payload)
            result["unit"] = "rad" if code == 0x0902 else "rad/s"
        else:
            # RobotStateUpload ABI alignment must be confirmed on real firmware.
            result["payload_hex"] = payload.hex()
            result["payload_bytes"] = len(payload)
    else:
        raise ValueError("Unsupported command type")
    return result


def load_config(path):
    with open(path, encoding="utf-8-sig") as stream:
        config = json.load(stream)
    for key in ("robot_ip", "listen_ip"):
        value = config.get(key)
        if value is not None:
            ipaddress.IPv4Address(value)
    for key in ("command_port", "listen_port"):
        value = config.get(key)
        if value is not None and (type(value) is not int or not 1 <= value <= 65535):
            raise ValueError(f"{key} must be an integer from 1 to 65535")
    return config


def listen(config, seconds):
    if not config.get("robot_ip") or not config.get("listen_port"):
        raise ValueError("Set robot_ip and listen_port in config.json first")
    bind_ip = config.get("listen_ip") or "0.0.0.0"
    deadline = time.monotonic() + seconds
    count = 0
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.bind((bind_ip, config["listen_port"]))
        print(f"Listening on {bind_ip}:{config['listen_port']} for {seconds}s; no commands sent")
        while time.monotonic() < deadline:
            sock.settimeout(max(0.001, min(0.5, deadline - time.monotonic())))
            try:
                packet, source = sock.recvfrom(65535)
            except socket.timeout:
                continue
            if source[0] != config["robot_ip"]:
                continue
            try:
                decoded = decode_packet(packet)
            except ValueError as exc:
                print(json.dumps({"source": source, "invalid": str(exc)}))
                continue
            print(json.dumps({"source": source, "packet": decoded}))
            count += 1
    print(f"Received {count} valid packets")
    return 0 if count else 2


def main():
    parser = argparse.ArgumentParser(description="Lite 3 offline packets and passive UDP telemetry")
    parser.add_argument("--config", default="config.json")
    commands = parser.add_subparsers(dest="action", required=True)
    preview = commands.add_parser("preview", help="Print bytes only; never sends")
    preview.add_argument("command", choices=COMMANDS)
    decode = commands.add_parser("decode", help="Decode a captured hexadecimal packet")
    decode.add_argument("hex_packet")
    commands.add_parser("check-config", help="Validate local configuration; no network access")
    receiver = commands.add_parser("listen", help="Passively receive UDP telemetry")
    receiver.add_argument("--seconds", type=int, default=10)
    args = parser.parse_args()
    try:
        if args.action == "preview":
            print(encode_simple(COMMANDS[args.command]).hex(" "))
            print("OFFLINE PREVIEW: no data sent")
        elif args.action == "decode":
            print(json.dumps(decode_packet(bytes.fromhex(args.hex_packet)), indent=2))
        elif args.action == "check-config":
            config = load_config(args.config)
            print(json.dumps(config, indent=2))
            missing = [key for key in ("robot_ip", "listen_port") if not config.get(key)]
            print("Missing for live reception: " + ", ".join(missing) if missing else "Ready for passive reception; connectivity not tested")
            return 2 if missing else 0
        else:
            if not 1 <= args.seconds <= 3600:
                raise ValueError("seconds must be between 1 and 3600")
            return listen(load_config(args.config), args.seconds)
    except (OSError, ValueError, TypeError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
