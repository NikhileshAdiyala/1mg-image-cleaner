import sys
import os

# Set U2NET_HOME to /tmp/.u2net for read-only serverless environment
os.environ["U2NET_HOME"] = "/tmp/.u2net"
os.environ["VERCEL"] = "1"
os.environ["NUMEXPR_MAX_THREADS"] = "1"
os.environ["OMP_NUM_THREADS"] = "1"

# Add project root to sys.path so 'app' package is found
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from app.main import app

# Vercel looks for 'app' or 'handler'
handler = app
