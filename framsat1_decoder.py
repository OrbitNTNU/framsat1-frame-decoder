"""FramSat-1 Telemetry and Frame Decoder.

Developed by Orbit NTNU (SatCom Team).
Licensed under MIT License.
"""

from datetime import datetime, timezone
import json
import socket
import struct
import sys



def parse_framsat_telemetry(payload_bytes: bytes):
  """Parses FramSat-1 Housekeeping Telemetry (starting with 'FS1.0')."""
  # 1. Health & Status Header (19 bytes, Big-Endian)
  # 5s: signature ("FS1.0")
  # B:  id (uint8_t)
  # B:  type (1=DEFAULT, 2=LEOP)
  # B:  rssi (uint8_t)
  # H:  telecommand_count (uint16_t)
  # B:  eps_flags (uint8_t)
  # H:  reboot_count (uint16_t)
  # H:  battery_voltage (uint16_t, mV)
  # I:  uptime_sec (uint32_t, seconds)
  fmt_health = ">5sBBBHBHHI"
  hdr_size = struct.calcsize(fmt_health)

  if len(payload_bytes) < hdr_size:
    print(f"   Payload Raw Hex: {payload_bytes.hex().upper()}")
    return

  sign, bcn_id, bcn_type, rssi, cmd_count, eps_flags, reboots, v_mv, uptime = (
      struct.unpack(fmt_health, payload_bytes[:hdr_size])
  )

  mode_str = (
      "LEOP (Launch / Deployment Mode)"
      if bcn_type == 2
      else "DEFAULT (Nominal Orbit)"
  )
  v_bat = v_mv / 1000.0
  uptime_hrs = uptime / 3600.0

  print("\n   ─── [ FramSat-1 Housekeeping Telemetry ] ───")
  print(f"   Signature:             {sign.decode('ascii', errors='replace')}")
  print(f"   Beacon ID:             #{bcn_id}")
  print(f"   Operating Mode:        {mode_str}")
  print(f"   Satellite Uplink RSSI: -{rssi} dBm")
  print(f"   Telecommands Accepted: {cmd_count}")
  print(f"   EPS Flags:             0x{eps_flags:02X}")
  print(f"   OBC / EPS Reboot Count:{reboots}")
  print(f"   Battery Voltage:       {v_bat:.3f} V ({v_mv} mV)")
  print(f"   Satellite Uptime:      {uptime} s ({uptime_hrs:.2f} hours)")

  # Strip the trailing 4-byte CRC-32 trailer from the frame if present
  raw_sensors = (
      payload_bytes[hdr_size:-4]
      if len(payload_bytes) >= hdr_size + 4
      else payload_bytes[hdr_size:]
  )

  # Check if in LEOP mode and sensor array is unpopulated (zero-padding)
  if bcn_type == 2 and all(b == 0 for b in raw_sensors):
    print(
        f"\n   ─── [ Attitude Sensors (LEOP Mode) ] ───\n   Status: "
        f"              Sensors unpowered during deployment ({len(raw_sensors)}"
        " bytes zero-padded)."
    )
    return

  # In Nominal Mode (or populated LEOP), unpack 20-byte sensor samples
  num_samples = len(raw_sensors) // 20
  if num_samples > 0:
    print(f"\n   ─── [ Attitude Sensors: {num_samples}x Samples ] ───")
    print(
        "   # | Time (s) | Sun Sensor GSS (a, b, c, d)      | Earth Sensor ESS"
        " (x, y, illum)"
    )
    print(
        "  "
        " ──+──────────+──────────────────────────────────+─────────────────────────────"
    )

    sample_fmt = ">BHHHHBBBBBHI"
    for i in range(min(num_samples, 9)):
      chunk = raw_sensors[i * 20 : (i + 1) * 20]
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
  """Parses a received frame (handles direct HDLC and AX.25 UI encapsulation)."""
  if len(frame_bytes) < 5:
    print("[-] Frame rejected: Length is less than 5 bytes.")
    return

  now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

  print("\n" + "=" * 65)
  print(f"🛰️  FramSat-1 Frame Received at {now_utc}")
  print(f"   Total Frame Length: {len(frame_bytes)} bytes")

  idx = frame_bytes.find(b"FS1.0")

  if idx != -1:
    print(f"   Telemetry Found:    Offset index {idx}")
    if idx >= 16:
      dest_call = "".join(chr(b >> 1) for b in frame_bytes[0:6]).strip()
      src_call = "".join(chr(b >> 1) for b in frame_bytes[7:13]).strip()
      print(f"   Encapsulation:      AX.25 UI-Frame ({src_call} -> {dest_call})")
    elif idx > 0:
      print(
          f"   Transport Header:   {frame_bytes[:idx].hex().upper()} ({idx}"
          " bytes)"
      )
    else:
      print("   Encapsulation:      Direct HDLC (Payload starts at offset 0)")

    parse_framsat_telemetry(frame_bytes[idx:])
  else:
    print(
        f"   Payload Text:      "
        f" '{frame_bytes.decode('latin-1', 'replace')}'"
    )
    print(f"   Payload Raw Hex:    {frame_bytes.hex().upper()}")

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
  # Verified On-Orbit SatNOGS Downlink Frame (LEOP Mode, 197 bytes)
  DEFAULT_TEST_FRAME = (
      "8500850000CF4653312E30B2020000000000011E57000012EF"
      + "00" * 168
      + "71B5004F"
  )

  if len(sys.argv) > 1:
    if sys.argv[1] == "--listen":
      listen_live_gnuradio()
    else:
      raw_hex = sys.argv[1].replace(" ", "")
      parse_framsat_frame(bytes.fromhex(raw_hex))
  else:
    print("[*] No arguments provided. Running test against verified LEOP frame:")
    parse_framsat_frame(bytes.fromhex(DEFAULT_TEST_FRAME))
    print("Usage:")
    print("  python3 framsat1_decoder.py <HEX_STRING>")
    print("  python3 framsat1_decoder.py --listen")