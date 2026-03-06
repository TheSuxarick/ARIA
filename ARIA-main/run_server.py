import os
import sys

script_dir = os.path.dirname(os.path.abspath(__file__))
website_dir = os.path.join(script_dir, "ARIA website")
sys.path.insert(0, website_dir)
os.chdir(website_dir)

from app import app, socketio
socketio.run(app, host="0.0.0.0", port=5000, debug=True, use_reloader=False)
