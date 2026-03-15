import pyaudio

p = pyaudio.PyAudio()
print("Devices:", p.get_device_count())
for i in range(p.get_device_count()):
    d = p.get_device_info_by_index(i)
    io = ""
    if d["maxInputChannels"] > 0:
        io += "IN"
    if d["maxOutputChannels"] > 0:
        io += " OUT"
    print(f"  [{i}] {io.strip():6s} {d['name']}")

try:
    di = p.get_default_input_device_info()
    print(f"Default input:  [{di['index']}] {di['name']}")
except Exception as e:
    print(f"Default input:  ERROR - {e}")

try:
    do = p.get_default_output_device_info()
    print(f"Default output: [{do['index']}] {do['name']}")
except Exception as e:
    print(f"Default output: ERROR - {e}")

try:
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                    output=True, frames_per_buffer=512)
    stream.write(b"\x00" * 1024)
    stream.close()
    print("Output stream: OK")
except Exception as e:
    print(f"Output stream: FAILED - {e}")

try:
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=16000,
                    input=True, frames_per_buffer=512)
    data = stream.read(512, exception_on_overflow=False)
    stream.close()
    print(f"Input stream:  OK ({len(data)} bytes)")
except Exception as e:
    print(f"Input stream:  FAILED - {e}")

p.terminate()
print("Done")
