# from yeelight import discover_bulbs

# # This scans your network and finds all Yeelight bulbs
# bulbs = discover_bulbs()

# for bulb in bulbs:
#     print(f"Found bulb: {bulb}")
#     print(f"  IP: {bulb['ip']}")
#     print(f"  Port: {bulb['port']}")
#     print(f"  Model: {bulb['capabilities'].get('model', 'unknown')}")



# 172.16.255.52
from yeelight import Bulb

# Replace with your bulb's IP address
bulb = Bulb("172.16.255.52")

# # Turn on
# bulb.turn_on()

# # Turn off
# bulb.turn_off()

# Toggle
bulb.toggle()

# # Set brightness (1-100)
# bulb.set_brightness(50)

# # Set color temperature (1700-6500K)
# bulb.set_color_temp(3000)

# # Set RGB color (red example)
# bulb.set_rgb(255, 0, 0)

# # Get bulb status
# properties = bulb.get_properties()
# print(properties)
