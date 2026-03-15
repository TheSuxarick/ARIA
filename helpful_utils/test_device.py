"""
ESP32 AI Assistant - Two-Way Audio Test

  PC mic       -> UDP -> ESP32 speaker
  ESP32 mic    -> UDP -> PC speakers

Usage:
  python test_device.py --esp32-ip 192.168.137.248
  python test_device.py                              # auto-detect
"""

import socket
import struct
import time
import threading
import argparse
import pyaudio


ESP32_PORT_RECV = 12345
ESP32_PORT_SEND = 12346
SAMPLE_RATE     = 16000
CHUNK           = 512

esp32_ip = None
esp32_ip_event = threading.Event()
stop_event = threading.Event()


def get_local_ips():
    ips = []
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.append(ip)
    except socket.gaierror:
        pass
    return sorted(set(ips))


def receive_esp32_mic(out_stream):
    """ESP32 mic -> PC speakers"""
    global esp32_ip

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind(("0.0.0.0", ESP32_PORT_RECV))
    except OSError:
        print(f"[ESP32 -> PC] ERROR: Port {ESP32_PORT_RECV} in use! Stop Flask server first.")
        return
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
    sock.settimeout(5.0)

    print(f"[ESP32 -> PC] Listening on 0.0.0.0:{ESP32_PORT_RECV}...")

    pkt_count = 0
    last_t = time.time()

    while not stop_event.is_set():
        try:
            data, addr = sock.recvfrom(4096)
        except socket.timeout:
            print(f"[ESP32 -> PC] No packets for 5s...")
            print(f"             PC IPs: {', '.join(get_local_ips())}")
            continue

        if esp32_ip is None and not esp32_ip_event.is_set():
            esp32_ip = addr[0]
            esp32_ip_event.set()
            print(f"[ESP32 -> PC] Auto-detected source: {esp32_ip}")

        pkt_count += 1
        now = time.time()
        if now - last_t >= 3.0:
            n = len(data) // 2
            samples = struct.unpack(f"<{n}h", data)
            peak = max(abs(s) for s in samples)
            print(f"[ESP32 -> PC] {pkt_count} pkts/3s | peak {peak}/32767")
            pkt_count = 0
            last_t = now

        try:
            out_stream.write(data)
        except Exception:
            pass

    sock.close()


def send_pc_mic(in_stream):
    """PC mic -> ESP32 speaker"""
    global esp32_ip

    print("[PC -> ESP32] Waiting for ESP32 IP...")
    if not esp32_ip_event.wait(timeout=60):
        print("[PC -> ESP32] Timed out. Use --esp32-ip.")
        return

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    print(f"[PC -> ESP32] Streaming to {esp32_ip}:{ESP32_PORT_SEND}")

    while not stop_event.is_set():
        try:
            data = in_stream.read(CHUNK, exception_on_overflow=False)
            sock.sendto(data, (esp32_ip, ESP32_PORT_SEND))
        except Exception:
            pass

    sock.close()


def main():
    global esp32_ip

    parser = argparse.ArgumentParser(description="Two-way audio test with ESP32")
    parser.add_argument("--esp32-ip", type=str, default=None)
    args = parser.parse_args()

    if args.esp32_ip:
        esp32_ip = args.esp32_ip
        esp32_ip_event.set()

    local_ips = get_local_ips()

    print("=" * 55)
    print("  Two-Way Audio Test")
    print("=" * 55)
    print(f"  PC IPs       : {', '.join(local_ips)}")
    print(f"  ESP32 -> PC  : port {ESP32_PORT_RECV}")
    print(f"  PC -> ESP32  : port {ESP32_PORT_SEND}")
    print(f"  Sample rate  : {SAMPLE_RATE} Hz")
    if args.esp32_ip:
        print(f"  ESP32 IP     : {args.esp32_ip}")
    else:
        print(f"  ESP32 IP     : auto-detect")
    print("=" * 55)
    print()

    p = pyaudio.PyAudio()

    out_stream = p.open(
        format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
        output=True, frames_per_buffer=CHUNK
    )
    print("[AUDIO] Speaker output opened")

    in_stream = p.open(
        format=pyaudio.paInt16, channels=1, rate=SAMPLE_RATE,
        input=True, frames_per_buffer=CHUNK
    )
    print("[AUDIO] Mic input opened")
    print()

    t1 = threading.Thread(target=receive_esp32_mic, args=(out_stream,), daemon=True)
    t2 = threading.Thread(target=send_pc_mic, args=(in_stream,), daemon=True)
    t1.start()
    t2.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping...")
        stop_event.set()
        time.sleep(0.5)
        in_stream.close()
        out_stream.close()
        p.terminate()
        print("Stopped.")


if __name__ == "__main__":
    main()
