"""Wait for the launcher's network setup before executing any project tool."""
import os
from pathlib import Path
import sys
import time

deadline = time.monotonic() + 45
while not (Path(sys.argv[1]) / 'ready').exists():
    if time.monotonic() > deadline:
        sys.exit('Sandbox setup timed out')
    time.sleep(0.05)
os.execvp(sys.argv[2], sys.argv[2:])
