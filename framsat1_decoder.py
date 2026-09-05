from datetime import datetime, timezone
import json
import socket
import struct
import sys

EXPECTED_CALLSIGN = "LA1ORB"


def parse_framsat_telemetry(payload_bytes: bytes):
  """Parses the FramSat-1 Housekeeping Telemetry struct (fs_bcn)."""
  # 1. Parse Health & Status Header (19 bytes)
  fmt_health = "<5sBBBHBHHI"
  hdr_size = struct.calcsize(fmt_health)

  if len(payload_bytes) < hdr_size:
    print(f"   Payload Raw Hex: {payload_bytes.hex().upper()}")
    return

  sign, bcn_id, bcn_type, rssi, cmd_heard, eps_mask, bootcount, battery, uptime = (
      struct.unpack(fmt_health, payload_bytes[:hdr_size])
  )

  mode_str = (
      "LEOP (Deployment)" if bcn_type == 2 else "DEFAULT (Nominal Orbit)"
  )
  v_bat = battery / 1000.0
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

  # 2. Parse 9x Payload Sensor Samples (GSS Sun Sensor & ESS Earth Sensor)
  sensor_bytes = payload_bytes[hdr_size:]
  num_samples = len(sensor_bytes) // 20

  if num_samples > 0:
    print(
        f"\n   ─── [ Payload: {num_samples}x Sensor Samples (GSS Sun & ESS"
        " Earth Sensors) ] ───"
    )
    print(
        "   # | Time (s) | Sun Sensor GSS (a, b, c, d)      | Earth Sensor ESS"
        " (x, y, illum)"
    )
    print(
        "  "
        " ──+──────────+──────────────────────────────────+─────────────────────────────"
    )

    # 1B (id) + 4H (gss) + 5B (ess) + 1H (sample_size) + 1I (time_sec) = 20 bytes!
    sample_fmt = "<BHHHHBBBBBHI"

    for i in range(min(num_samples, 9)):
      chunk = sensor_bytes[i * 20 : (i + 1) * 20]
      if len(chunk) == 20:
        (
            s_id,
            g_a,
            g_b,
            g_c,
            g_d,
            e_x,
            e_y,
            i1,
            i2,
            i3,
            s_size,
            s_time,
        ) = struct.unpack(sample_fmt, chunk)
        gss_str = f"{g_a:4d}, {g_b:4d}, {g_c:4d}, {g_d:4d}"
        ess_str = f"X={e_x:3d}, Y={e_y:3d}, Illum=[{i1},{i2},{i3}]"
        print(f"   {i+1:1d} | {s_time:<8d} | {gss_str:<32s} | {ess_str}")


def parse_framsat_frame(frame_bytes: bytes):
  """Parses a received frame (handles both direct HDLC and AX.25 UI frames)."""
  if len(frame_bytes) < 5:
    print("[-] Frame rejected: Length is less than 5 bytes.")
    return

  now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

  print("\n" + "=" * 65)
  print(f"🛰️  FramSat-1 Frame Received at {now_utc}")
  print(f"   Total Frame Length: {len(frame_bytes)} bytes")

  # CASE 1: Direct HDLC beacon from real satellite (starts with "FS1.0" at byte 0)
  if frame_bytes.startswith(b"FS1.0"):
    print("   Framing Type:       Direct HDLC (No AX.25 callsign header)")
    parse_framsat_telemetry(frame_bytes)

  # CASE 2: Encapsulated in AX.25 UI-frame (starts with "FS1.0" at byte 16)
  elif len(frame_bytes) >= 16 and frame_bytes[16:].startswith(b"FS1.0"):
    dest_call = "".join(chr(b >> 1) for b in frame_bytes[0:6]).strip()
    src_call = "".join(chr(b >> 1) for b in frame_bytes[7:13]).strip()
    control_byte = frame_bytes[14]
    pid_byte = frame_bytes[15]

    print("   Framing Type:       AX.25 UI-Frame")
    print(f"   Destination:        {dest_call}")
    print(f"   Source:             {src_call} (Expected: {EXPECTED_CALLSIGN})")
    print(f"   Control:            0x{control_byte:02X} (UI-Frame)")
    print(f"   PID:                0x{pid_byte:02X}")
    parse_framsat_telemetry(frame_bytes[16:])

  # CASE 3: Generic text or raw payload
  else:
    print(
        f"   Payload Text:      "
        f" '{frame_bytes.decode('latin-1', 'replace')}'"
    )
    print(f"   Payload Hex:        {frame_bytes.hex().upper()}")

  print("=" * 65 + "\n")


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
  FULL_TEST_FRAME = (
      "86A240404040609882629EA4846103F04653312E3001015500000002003A20100E0000"
      "0100045203D2002D007854FFF0B41400060E0000"
      "021A044E03C80032007A52FFF1B51400080E0000"
      "0330044503BE0037007D50FEF2B614000A0E0000"
      "0445043C03B5003C00804DFDF3B714000C0E0000"
      "055A043303AC004100824BFCF4B814000E0E0000"
      "066F042A03A20046008549FBF5B91400100E0000"
      "078404210399004B008747FAF6BA1400120E0000"
      "0899041803900050008A45F9F7BB1400140E0000"
      "09AE040F03860055008C43F8F8BC1400160E0000"
  )

  if len(sys.argv) > 1:
    if sys.argv[1] == "--listen":
      listen_live_gnuradio()
    else:
      raw_hex = sys.argv[1].replace(" ", "")
      parse_framsat_frame(bytes.fromhex(raw_hex))
  else:
    print("[*] Running verification against full 215-byte test vector:\n")
    parse_framsat_frame(bytes.fromhex(FULL_TEST_FRAME))