from datetime import datetime, timezone
import json
import socket
import struct
import sys

EXPECTED_CALLSIGN = "LA1ORB"


def parse_framsat_telemetry(payload_bytes: bytes):
  """Parses the FramSat-1 Housekeeping Telemetry struct (fs_bcn)."""
  # fs_bcn header format:
  # 5s: sign ("FS1.0")
  # B:  id (uint8_t)
  # B:  type (enum fs_bcn_type: 1=DEFAULT, 2=LEOP)
  # B:  rssi (uint8_t)
  # H:  cmd_heard (uint16_t, little-endian)
  # B:  eps.mask (uint8_t)
  # H:  eps.bootcount (uint16_t, little-endian)
  # H:  eps.battery (uint16_t, mV, little-endian)
  # I:  time_sec (uint32_t, uptime seconds, little-endian)
  fmt = "<5sBBBHBHHI"
  hdr_size = struct.calcsize(fmt)

  if len(payload_bytes) < hdr_size:
    print(f"   Payload Raw Hex: {payload_bytes.hex().upper()}")
    return

  sign, bcn_id, bcn_type, rssi, cmd_heard, eps_mask, bootcount, battery, uptime = (
      struct.unpack(fmt, payload_bytes[:hdr_size])
  )

  mode_str = (
      "LEOP (Deployment)" if bcn_type == 2 else "DEFAULT (Nominal Orbit)"
  )
  v_bat = battery / 1000.0  # Convert mV to V
  uptime_hrs = uptime / 3600.0

  print("\n   ─── [ FramSat-1 Housekeeping Telemetry ] ───")
  print(f"   Signature:          {sign.decode('ascii', errors='replace')}")
  print(f"   Beacon ID:          #{bcn_id}")
  print(f"   Operating Mode:     {mode_str}")
  print(f"   Satellite RX RSSI:  -{rssi} dBm")
  print(f"   Telecommands Heard: {cmd_heard}")
  print(f"   EPS Reboot Count:   {bootcount}")
  print(f"   Battery Voltage:    {v_bat:.3f} V ({battery} mV)")
  print(f"   Satellite Uptime:   {uptime} s ({uptime_hrs:.2f} hours)")

  payload_data = payload_bytes[hdr_size:]
  if len(payload_data) > 0:
    print(
        f"   Payload Sensor Data:{len(payload_data)} bytes (GSS/ESS raw sensor"
        " array)"
    )


def parse_framsat_frame(frame_bytes: bytes):
  """Parses a received AX.25 UI frame."""
  if len(frame_bytes) < 16:
    print("[-] Frame rejected: Length is less than 16 bytes.")
    return

  # AX.25 address fields (reverse 1-bit left-shift)
  dest_call = "".join(chr(b >> 1) for b in frame_bytes[0:6]).strip()
  src_call = "".join(chr(b >> 1) for b in frame_bytes[7:13]).strip()
  control_byte = frame_bytes[14]
  pid_byte = frame_bytes[15]
  payload_raw = frame_bytes[16:]

  now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

  print("\n" + "=" * 55)
  print(f"🛰️  FramSat-1 Frame Received at {now_utc}")
  print(f"   Destination:        {dest_call}")
  print(f"   Source:             {src_call} (Expected: {EXPECTED_CALLSIGN})")
  print(f"   Control:            0x{control_byte:02X} (UI-Frame)")
  print(f"   PID:                0x{pid_byte:02X}")
  print(f"   Total Frame Length: {len(frame_bytes)} bytes")

  # Detect if payload is a FramSat-1 Housekeeping Beacon ("FS1.0")
  if payload_raw.startswith(b"FS1.0"):
    parse_framsat_telemetry(payload_raw)
  else:
    # Generic / Custom ASCII Payload
    print(f"   Payload Text:       '{payload_raw.decode('latin-1', 'replace')}'")
    print(f"   Payload Hex:        {payload_raw.hex().upper()}")

  print("=" * 55 + "\n")


def listen_live_gnuradio(host="127.0.0.1", port=52001):
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
  if len(sys.argv) > 1:
    if sys.argv[1] == "--listen":
      listen_live_gnuradio()
    else:
      raw_hex = sys.argv[1].replace(" ", "")
      parse_framsat_frame(bytes.fromhex(raw_hex))
  else:
    # Default test vector: Valid AX.25 frame with simulated FS1.0 telemetry
    # Battery: 8.250V (8250 mV = 0x203A), Uptime: 3600s (0x0E10), Bootcount: 2
    mock_frame_hex = (
        "86A240404040609882629EA4846103F04653312E3001015500000002003A20100E0000"
    )
    print("[*] Running verification against built-in test vector:\n")
    parse_framsat_frame(bytes.fromhex(mock_frame_hex))
    print("Usage:")
    print("  python3 framsat1_decoder.py <HEX_STRING>")
    print("  python3 framsat1_decoder.py --listen")