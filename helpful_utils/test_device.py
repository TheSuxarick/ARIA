"""
ESP32 AI Assistant — Two-Way Audio Test

  PC mic       → UDP → ESP32 speaker
  ESP32 mic    → UDP → PC speakers

Usage:
  python test_device.py                          # auto-detect ESP32 IP
  python test_device.py --esp32-ip 10.72.61.202  # specify ESP32 IP
"""

import socket
import struct
import time
import threading
import argparse
import pyaudio

ESP32_PORT_RECV  = 12345   # PC receives ESP32 mic audio here
ESP32_PORT_SEND  = 12346   # PC sends PC mic audio to ESP32 here
SAMPLE_RATE      = 16000
CHUNK            = 512

esp32_ip = None
esp32_ip_event = threading.Event()


def receive_esp32_mic():
    """ESP32 mic → PC speakers"""
    global esp32_ip

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", ESP32_PORT_RECV))
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                    output=True, frames_per_buffer=CHUNK)

    print(f"[ESP32 → PC] Listening on port {ESP32_PORT_RECV}...")

    pkt_count = 0
    last_t = time.time()

    while True:
        data, addr = sock.recvfrom(4096)

        if esp32_ip is None:
            esp32_ip = addr[0]
            esp32_ip_event.set()
            print(f"[ESP32 → PC] ESP32 found at {esp32_ip}")

        pkt_count += 1
        now = time.time()
        if now - last_t >= 3.0:
            samples = struct.unpack(f"<{len(data)//2}h", data)
            peak = max(abs(s) for s in samples)
            print(f"[ESP32 → PC] {pkt_count} pkts/3s | peak {peak}/32767")
            pkt_count = 0
            last_t = now

        stream.write(data)


def send_pc_mic():
    """PC mic → ESP32 speaker"""
    global esp32_ip

    print("[PC → ESP32] Waiting for ESP32 IP...")
    if not esp32_ip_event.wait(timeout=30):
        print("[PC → ESP32] Timed out. Use --esp32-ip.")
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
                    input=True, frames_per_buffer=CHUNK)

    print(f"[PC → ESP32] Streaming PC mic to {esp32_ip}:{ESP32_PORT_SEND}")

    while True:
        data = stream.read(CHUNK, exception_on_overflow=False)
        sock.sendto(data, (esp32_ip, ESP32_PORT_SEND))


def main():
    global esp32_ip

    parser = argparse.ArgumentParser(description="Two-way audio test with ESP32")
    parser.add_argument("--esp32-ip", type=str, default=None,
                        help="ESP32 IP address (auto-detected if not set)")
    args = parser.parse_args()

    if args.esp32_ip:
        esp32_ip = args.esp32_ip
        esp32_ip_event.set()

    print("=" * 50)
    print("  Two-Way Audio Test")
    print("=" * 50)
    print(f"  ESP32 mic  → PC speakers  (port {ESP32_PORT_RECV})")
    print(f"  PC mic     → ESP32 speaker (port {ESP32_PORT_SEND})")
    print(f"  Sample rate: {SAMPLE_RATE} Hz")
    print("=" * 50 + "\n")

    t1 = threading.Thread(target=receive_esp32_mic, daemon=True)
    t2 = threading.Thread(target=send_pc_mic, daemon=True)
    t1.start()
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
