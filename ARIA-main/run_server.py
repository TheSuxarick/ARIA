import os
import sys

# Change to the ARIA website directory
script_dir = os.path.dirname(os.path.abspath(__file__))
website_dir = os.path.join(script_dir, "ARIA website")
os.chdir(website_dir)
sys.path.insert(0, website_dir)

# Import and run the Flask app
from app import app
app.run(debug=True, port=5000)
