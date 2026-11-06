# -*- coding: utf-8 -*-
"""
Rad-score tool launcher.
Starts the Streamlit server (hidden, if not already running) and opens the browser.
Run with the Python 3.13 interpreter, or just double-click the desktop shortcut.
"""
import os
import sys
import time
import socket
import argparse
import subprocess
import webbrowser

from paths import find_py313

TOOL = os.path.dirname(os.path.abspath(__file__))
HOST = "127.0.0.1"
PORT = 8501
URL = f"http://{HOST}:{PORT}"


def port_open(port):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect((HOST, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    if not port_open(PORT):
        app = os.path.join(TOOL, "app.py")
        py = find_py313() or sys.executable
        cmd = [py, "-m", "streamlit", "run", app,
               "--server.port", str(PORT), "--server.address", HOST,
               "--server.headless", "true"]
        kwargs = {}
        if os.name == "nt":
            kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
        subprocess.Popen(cmd, cwd=TOOL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, **kwargs)
        for _ in range(60):
            time.sleep(0.5)
            if port_open(PORT):
                break

    if not args.no_browser:
        webbrowser.open(URL)


if __name__ == "__main__":
    main()
