"""
Entry point for hosts that expect a `main.py` at the project root.

Some panels (Pterodactyl and the hosts built on it, such as Wispbyte) look
for `main.py` when deploying and refuse to start without it. The bot itself
lives in bot.py, so this just runs that file as __main__.

It also fixes up sys.path and the working directory first, because those
panels do not always start the process from the project root.
"""

import os
import runpy
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

if HERE not in sys.path:
    sys.path.insert(0, HERE)

os.chdir(HERE)

runpy.run_path(os.path.join(HERE, "bot.py"), run_name="__main__")
