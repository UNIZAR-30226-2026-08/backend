import argparse
import subprocess
import sys
import platform
import os

def launch_terminal(command_args):
    """
    Attempts to launch a new terminal window running the specified command.
    Tries common terminal emulators like kitty, foot, and xterm.

    Args:
        command_args (list[str]): The command and its arguments to run in the new terminal.

    Returns:
        None
    """
    command_str = " ".join(command_args)
    full_command = f"{command_str}; printf '\\n--- Process Finished ---\\n'; read -p 'Press Enter to exit...'"
    print(command_str)

    terminals = [
        ("kitty", []),
        ("foot", []),
        ("xterm", ["-e"])
    ]

    for term, flags in terminals:
        try:
            cmd = [term] + flags + ["sh", "-c", full_command]
            subprocess.Popen(cmd)
            return
        except FileNotFoundError:
            continue

    print(f"Could not launch a terminal. Run manually: {command_str}")

def main():
    """
    Main entry point for the test runner script.
    Parses arguments for two players and launches two client terminals in either public or private mode.

    Args:
        None

    Returns:
        None
    """
    parser = argparse.ArgumentParser(description="Run two CLI clients for testing")
    parser.add_argument("--url", default="ws://localhost:8000", help="WebSocket URL")
    parser.add_argument("--token1", help="JWT Access token for Player 1", required=True)
    parser.add_argument("--player_id1", help="Player ID for Player 1", required=True)
    parser.add_argument("--token2", help="JWT Access token for Player 2", required=True)
    parser.add_argument("--player_id2", help="Player ID for Player 2", required=True)
    parser.add_argument("--mode", choices=["public", "private"], default="public", help="Matchmaking mode")
    args = parser.parse_args()

    if args.mode == "public":
        cmd1 = [sys.executable, "scripts/client.py", "--url", args.url, "--token", args.token1, "--player_id", args.player_id1, "--mode", "public"]
        cmd2 = [sys.executable, "scripts/client.py", "--url", args.url, "--token", args.token2, "--player_id", args.player_id2, "--mode", "public"]
    elif args.mode == "private":
        cmd1 = [sys.executable, "scripts/client.py", "--url", args.url, "--token", args.token1, "--player_id", args.player_id1, "--mode", "create"]
        cmd2 = [sys.executable, "scripts/client.py", "--url", args.url, "--token", args.token2, "--player_id", args.player_id2, "--mode", "join"]

    print("\nTwo terminals will launch...")
    launch_terminal(cmd1)
    launch_terminal(cmd2)

    print("\nTwo terminal windows should have opened.")
    print("If they didn't, open two new terminal tabs and run the following commands manually:")
    print(f"Player 1: {' '.join(cmd1)}")
    print(f"Player 2: {' '.join(cmd2)}")

if __name__ == "__main__":
    main()
