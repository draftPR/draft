#!/usr/bin/env python3
"""Test agent CLI streaming."""

import subprocess
from pathlib import Path

def test_agent_streaming():
    """Test cursor-agent streaming with a real prompt."""
    print("Testing cursor-agent streaming...")

    # Get repo root
    repo_root = Path(__file__).parent.parent
    agent_path = Path.home() / ".local/bin/cursor-agent"

    # Simple prompt
    prompt = """Analyze this repository and list 3 files you see. Output in JSON:
{"files": ["file1", "file2", "file3"]}"""

    cmd = [str(agent_path), "--print", "--workspace", str(repo_root), prompt]

    print(f"Running: {' '.join(cmd[:3])} <prompt>")
    print("Waiting for output...\n")

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

    process.wait(timeout=60)

    print(f"\nReceived {len(received_lines)} lines")
    print(f"Return code: {process.returncode}")

    if len(output_lines) > 0:
        print("\nFull output:")
        print("".join(output_lines[:50]))  # First 50 lines

if __name__ == "__main__":
    test_agent_streaming()
