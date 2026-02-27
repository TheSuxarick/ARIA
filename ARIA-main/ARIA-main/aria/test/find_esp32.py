"""
Find ESP32-CAM on the network by MAC address
MAC: 88:13:bf:6c:60:94
"""
import subprocess
import re
import socket

TARGET_MAC = "88:13:bf:6c:60:94"

print("="*50)
print("Finding ESP32-CAM on network")
print(f"Looking for MAC: {TARGET_MAC}")
print("="*50)

# Get local IP to determine network range
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    finally:
        s.close()
    return ip

local_ip = get_local_ip()
print(f"\nYour IP: {local_ip}")

# Get network prefix (e.g., 192.168.1)
network_prefix = '.'.join(local_ip.split('.')[:-1])
print(f"Network: {network_prefix}.0/24")

# Method 1: Check ARP cache first
print("\n[1] Checking ARP cache...")
try:
    result = subprocess.run(['arp', '-a'], capture_output=True, text=True)
    lines = result.stdout.lower()
    
    # Look for MAC address (with different separators)
    mac_variants = [
        TARGET_MAC.lower(),
        TARGET_MAC.lower().replace(':', '-'),
    ]
    
    for line in result.stdout.split('\n'):
        line_lower = line.lower()
        for mac in mac_variants:
            if mac in line_lower:
                # Extract IP from this line
                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                if ip_match:
                    found_ip = ip_match.group(1)
                    print(f"    FOUND in ARP cache: {found_ip}")
                    print(f"\n>>> ESP32-CAM IP: {found_ip}")
                    exit(0)
    
    print("    Not found in ARP cache")
except Exception as e:
    print(f"    Error: {e}")

# Method 2: Ping scan the network
print(f"\n[2] Scanning network {network_prefix}.1-254...")
print("    (This may take a minute...)")

# Ping all IPs to populate ARP cache
for i in range(1, 255):
    ip = f"{network_prefix}.{i}"
    subprocess.Popen(
        ['ping', '-n', '1', '-w', '100', ip],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

import time
time.sleep(5)  # Wait for pings to complete

# Check ARP cache again
print("\n[3] Checking ARP cache after scan...")
result = subprocess.run(['arp', '-a'], capture_output=True, text=True)

for line in result.stdout.split('\n'):
    line_lower = line.lower()
    for mac in mac_variants:
        if mac in line_lower:
            ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
            if ip_match:
                found_ip = ip_match.group(1)
                print(f"    FOUND: {found_ip}")
                print(f"\n>>> ESP32-CAM IP: {found_ip}")
                
                # Test if it's actually the camera
                print(f"\n[4] Testing camera at {found_ip}...")
                try:
                    import requests
                    resp = requests.get(f"http://{found_ip}:81/stream", timeout=3, stream=True)
                    if resp.status_code == 200:
                        print(f"    Camera stream is accessible!")
                    resp.close()
                except:
                    print(f"    Could not connect to camera stream")
                
                exit(0)

print("\n[!] ESP32-CAM not found on network")
print("\nTroubleshooting:")
print("1. Make sure ESP32-CAM is powered on")
print("2. Check if it's connected to the same WiFi network")
print("3. Try restarting the ESP32-CAM")
print(f"4. Your network is {network_prefix}.x - is ESP32 on same network?")
