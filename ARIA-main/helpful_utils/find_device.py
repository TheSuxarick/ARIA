"""
Find known devices on the local network by MAC address.

Scans the ARP table (with optional ping sweep) and reports
which of your registered devices are online.

Usage:
  python find_device.py            # find all known devices
  python find_device.py --sweep    # force a ping sweep first
"""

import socket
import subprocess
import re
import sys
import argparse

DEVICES = {
    "88:13:bf:6c:60:94": "Camera",
    "9c:9c:1f:e9:96:f4": "Speaker",
    "ac:15:a2:7f:aa:f6": "Router",
    "8c:b8:7e:90:65:50": "PC",
    "c4:93:bb:20:3a:29": "Lamp",
}


def get_local_subnet() -> tuple[str, str]:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
    finally:
        s.close()
    prefix = ".".join(local_ip.split(".")[:3])
    return local_ip, prefix


def parse_arp_table() -> dict[str, str]:
    """Return {normalized_mac: ip} for every entry in the OS ARP cache."""
    result = {}
    try:
        output = subprocess.check_output(["arp", "-a"], text=True)
        for line in output.splitlines():
            ip_match = re.search(r"(\d+\.\d+\.\d+\.\d+)", line)
            mac_match = re.search(r"([\da-fA-F]{2}[:-]){5}[\da-fA-F]{2}", line)
            if ip_match and mac_match:
                mac = mac_match.group(0).lower().replace("-", ":")
                result[mac] = ip_match.group(1)
    except Exception:
        pass
    return result


def ping_sweep(prefix: str):
    print(f"Ping sweep {prefix}.1-254 ...")
    procs = []
    for i in range(1, 255):
        proc = subprocess.Popen(
            ["ping", "-n", "1", "-w", "300", f"{prefix}.{i}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        procs.append(proc)
    for proc in procs:
        proc.wait()
    print()


def find_devices(force_sweep: bool = False) -> dict[str, dict]:
    local_ip, prefix = get_local_subnet()
    print(f"Local IP : {local_ip}")
    print(f"Subnet   : {prefix}.0/24\n")

    if force_sweep:
        ping_sweep(prefix)

    arp = parse_arp_table()

    found_any = False
    results = {}
    for mac, name in DEVICES.items():
        mac_norm = mac.lower()
        ip = arp.get(mac_norm)
        results[mac] = {"name": name, "ip": ip}
        if ip:
            found_any = True

    if not found_any and not force_sweep:
        print("Nothing in ARP cache. Running ping sweep...\n")
        ping_sweep(prefix)
        arp = parse_arp_table()
        for mac in results:
            results[mac]["ip"] = arp.get(mac.lower())

    return results


def main():
    parser = argparse.ArgumentParser(description="Find known devices by MAC")
    parser.add_argument("--sweep", action="store_true",
                        help="Force a ping sweep before checking")
    args = parser.parse_args()

    results = find_devices(force_sweep=args.sweep)

    name_width = max(len(r["name"]) for r in results.values())

    print(f"{'Device':<{name_width}}   {'MAC':<19}  {'IP'}")
    print("-" * (name_width + 40))

    online = 0
    for mac, info in results.items():
        status = info["ip"] if info["ip"] else "-- offline --"
        if info["ip"]:
            online += 1
        print(f"{info['name']:<{name_width}}   {mac:<19}  {status}")

    print(f"\n{online}/{len(results)} devices online.")


if __name__ == "__main__":
    main()
