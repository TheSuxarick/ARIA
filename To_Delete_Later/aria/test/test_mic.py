"""
Find any working microphone
"""
import sounddevice as sd
import numpy as np
import time

print("="*50)
print("SEARCHING FOR WORKING MICROPHONE")
print("="*50)

# Get all devices with input channels
devices = sd.query_devices()
input_devices = []

for i, d in enumerate(devices):
    if d['max_input_channels'] > 0:
        input_devices.append((i, d['name'][:40]))

print(f"\nFound {len(input_devices)} input devices. Testing each...")
print("(Say something during each test!)\n")

working = []

for device_id, name in input_devices:
    try:
        # Try to open and record
        audio = sd.rec(
            16000,  # 1 second at 16kHz
            samplerate=16000,
            channels=1,
            dtype='float32',
            device=device_id
        )
        time.sleep(1)
        sd.wait()
        
        volume = np.abs(audio).mean()
        
        if volume > 0.001:
            print(f"  [{device_id}] {name} - WORKS! (vol: {volume:.4f})")
            working.append((device_id, name, volume))
        else:
            print(f"  [{device_id}] {name} - no signal")
            
    except Exception as e:
        err = str(e)[:30]
        print(f"  [{device_id}] {name} - error: {err}")

print("\n" + "="*50)

if working:
    print("WORKING MICROPHONES:")
    for d, n, v in sorted(working, key=lambda x: -x[2]):
        print(f"  Device {d}: {n}")
    
    best_id = sorted(working, key=lambda x: -x[2])[0][0]
    print(f"\n>>> USE DEVICE {best_id}")
else:
    print("NO WORKING MICROPHONE FOUND!")
    print("\nTry these steps:")
    print("1. Windows Settings > Privacy & Security > Microphone")
    print("2. Turn ON 'Microphone access'")
    print("3. Turn ON 'Let apps access your microphone'")
    print("4. Check if your microphone is muted in taskbar")
