#!/usr/bin/env python3
"""Auto-commit and push script for smart-home-dashboard project."""
import os
import subprocess
import sys
import re
import tempfile

PROJECT_PATH = "/root/.hermes/projects/smart-home-dashboard"
GITHUB_USER = "riggles07"
REPO_NAME = "smart-home-dashboard"
BRANCH = "main"

def get_github_token():
    """Read token from Hermes env file."""
    env_path = os.path.expanduser("~/.hermes/.env")
    token = None
    with open(env_path, "r") as f:
        for line in f:
            if line.startswith("GITHUB_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break
    if not token:
        print("ERROR: GITHUB_TOKEN not found in ~/.hermes/.env")
        sys.exit(1)
    return token

def run_command(cmd, cwd=None, env=None):
    """Run command and return success status."""
    result = subprocess.run(
        cmd,
        shell=True,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env
    )
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr, file=sys.stderr)
    return result.returncode == 0

def main():
    os.chdir(PROJECT_PATH)
    
    # Check for changes
    result = subprocess.run(
        "git status --porcelain",
        shell=True,
        capture_output=True,
        text=True
    )
    changes = result.stdout.strip()
    
    if not changes:
        print("✅ No changes - skipping commit")
        return 0
    
    print("📝 Detected changes:")
    print(changes)
    print()
    
    # Stage all changes
    print("🔧 Staging changes...")
    run_command("git add .")
    
    # Create commit
    print("💾 Creating commit...")
    run_command('git commit -m "Auto-commit: Smart Home Dashboard updates"')
    
    # Push using ephemeral GIT_ASKPASS pattern
    print("🚀 Pushing to GitHub...")
    token = get_github_token()
    
    # Create ephemeral askpass script
    askpass = tempfile.mktemp(suffix=".sh")
    with open(askpass, "w") as f:
        f.write(f'''#!/bin/sh
case "$1" in
  Username*) echo x-access-token ;;
  Password*) echo {token} ;;
esac
''')
    os.chmod(askpass, 0o700)
    
    env = os.environ.copy()
    env["GIT_ASKPASS"] = askpass
    env["GIT_TERMINAL_PROMPT"] = "0"
    
    result = subprocess.run(
        ["git", "-c", "credential.helper=", "push", "-u", "origin", BRANCH],
        cwd=PROJECT_PATH,
        capture_output=True,
        text=True,
        env=env
    )
    
    # Clean up askpass
    os.unlink(askpass)
    
    if result.returncode == 0:
        print("✅ Push successful!")
        if result.stdout:
            print(result.stdout)
        return 0
    else:
        print("❌ Push failed!")
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
