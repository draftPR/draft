#!/usr/bin/env python3
"""Test subprocess streaming directly."""

import subprocess
from pathlib import Path


def test_subprocess_streaming():
    """Test that subprocess.Popen can stream output."""
    print("Testing subprocess streaming...")

    # Get repo root
    repo_root = Path(__file__).parent.parent

    # Simple test command that produces output
    cmd = ["echo", "Line 1\nLine 2\nLine 3"]

    received_lines = []

    def stream_callback(line: str):
        print(f"CALLBACK: {line}")
        received_lines.append(line)

    # Test with Popen and line-by-line reading
    process = subprocess.Popen(
        cmd,
        cwd=repo_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # Line buffered
    )

    output_lines = []
    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            output_lines.append(line)
            stream_callback(line.rstrip())

    process.wait()

    print(f"\nReceived {len(received_lines)} lines")
    print(f"Return code: {process.returncode}")


if __name__ == "__main__":
    test_subprocess_streaming()
