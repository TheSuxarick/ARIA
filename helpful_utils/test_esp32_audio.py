"""
Test: receive UDP audio from ESP32 mic and report signal levels.
Run this INSTEAD of the Flask server (only one thing can bind port 12345).

Stop the Flask server first, then:  python test_esp32_audio.py
"""

import socket
import struct
import time
import sys

UDP_PORT = 12345
RATE = 16000
DURATION = 10  # seconds to test

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
sock.settimeout(5.0)
sock.bind(("0.0.0.0", UDP_PORT))

print(f"Listening on UDP port {UDP_PORT} for {DURATION}s ...")
print(f"Waiting for ESP32 packets...\n")

start = time.time()
total_packets = 0
total_samples = 0
global_peak = 0
last_print = 0

try:
    while time.time() - start < DURATION:
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            print("  [!] No packet received for 5s — is ESP32 powered on and on the same network?")
            continue

        total_packets += 1
        n_samples = len(data) // 2
        total_samples += n_samples
        samples = struct.unpack(f"<{n_samples}h", data)
        peak = max(abs(s) for s in samples)
        if peak > global_peak:
            global_peak = peak

        now = time.time()
        if now - last_print >= 1.0:
            elapsed = now - start
            bar_len = min(peak * 50 // 32767, 50)
            bar = "#" * bar_len + "-" * (50 - bar_len)
            print(f"  [{elapsed:5.1f}s] from {addr[0]}:{addr[1]} | pkt#{total_packets:>5} | "
                  f"{len(data):>4}B | peak {peak:>5}/32767 |{bar}|")
            last_print = now

except KeyboardInterrupt:
    pass

sock.close()

print(f"\n{'='*60}")
print(f"  Total packets : {total_packets}")
print(f"  Total samples : {total_samples}")
print(f"  Global peak   : {global_peak} / 32767  ({global_peak*100/32767:.1f}%)")
print(f"{'='*60}")

if total_packets == 0:
    print("\n  RESULT: NO PACKETS received.")
    print("  Check: ESP32 powered? Same WiFi? PC_IP correct in firmware?")
elif global_peak < 50:
    print("\n  RESULT: Packets received but audio is SILENT (peak < 50).")
    print("  Check: INMP441 wiring, L/R pin to GND, SD pin to GPIO32.")
elif global_peak < 500:
    print("\n  RESULT: Very quiet signal. Mic may be working but gain is very low.")
    print("  Try speaking loudly or tapping near the mic.")
else:
    print(f"\n  RESULT: Audio stream looks GOOD. Mic is working.")
