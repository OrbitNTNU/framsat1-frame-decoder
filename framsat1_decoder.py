import socket
import sys


def parse_framsat_frame(frame_bytes: bytes):
  """Parses a raw AX.25 UI frame received from FramSat-1."""
  if len(frame_bytes) < 16:
    print("[-] Frame rejected: Length less than 16 bytes.")
    return

  # Extract callsigns (reverse the 1-bit left-shift)
  dest_call = "".join(chr(b >> 1) for b in frame_bytes[0:6]).strip()
  src_call = "".join(chr(b >> 1) for b in frame_bytes[7:13]).strip()

  control_byte = frame_bytes[14]
  pid_byte = frame_bytes[15]

  # Payload starts strictly at byte index 16
  payload_raw = frame_bytes[16:]
  payload_ascii = payload_raw.decode("latin-1", errors="replace")

  print("\n" + "=" * 50)
  print("🛰️  FramSat-1 Frame Decoded")
  print(f" Destination: {dest_call}")
  print(f" Source:      {src_call} (Expected: LA1ORB)")
  print(f" Control:     0x{control_byte:02X} (UI-Frame)")
  print(f" PID:         0x{pid_byte:02X}")
  print(f" Payload Len: {len(payload_raw)} bytes")
  print(f" Payload Text:'{payload_ascii}'")
  print(f" Payload Hex: {payload_raw.hex().upper()}")
  print("=" * 50)


def listen_live_gnuradio(host="127.0.0.1", port=52001):
  """Connects to GNU Radio's Socket PDU and decodes packets live."""
  print(f"[*] Connecting to GNU Radio Socket PDU at {host}:{port}...")
  try:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    print("[+] Connected! Listening for live satellite passes...\n")
    while True:
      data = s.recv(1024)
      if not data:
        break
      parse_framsat_frame(data)
  except Exception as e:
    print(f"[-] Connection failed: {e}")
  finally:
    s.close()


if __name__ == "__main__":
  # 1. If an argument is provided, parse that hex string directly
  if len(sys.argv) > 1:
    if sys.argv[1] == "--listen":
      listen_live_gnuradio()
    else:
      raw_hex = sys.argv[1].replace(" ", "")
      parse_framsat_frame(bytes.fromhex(raw_hex))
  else:
    # 2. Default: Run test on verification vector
    print("[*] No arguments provided. Running test verification vector:")
    example_hex = "86A240404040609882629C8EA66103F0534354657374"
    parse_framsat_frame(bytes.fromhex(example_hex))
    print(
        "\nUsage:\n  python parse_framsat.py <HEX_DATA>     (Decode a specific frame)"
    )
    print(
        "  python parse_framsat.py --listen        (Listen live to GNU Radio on port"
        " 52001)"
    )
