import sys, platform
# Allow running both as a package (recommended: `python -m timetracker ...`)
# and as a script from inside the package directory (`python main.py ...`).
try:
    from .logging_setup import get_logger
    from . import report
except Exception:
    # fallback to non-package imports when running main.py directly
    from logging_setup import get_logger
    import report

logger = get_logger("tt.main")

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("python -m timetracker start")
        print("  python -m timetracker report [days]")
        return

    cmd = sys.argv[1].lower()

    if cmd == "start":
        if platform.system() == "Windows":
            from .platform.windows import run as run_win
            run_win()
        elif platform.system() == "Darwin":
            from .platform.macos import run as run_mac
            run_mac()
        else:
            print("Unsupported OS for this project.")
    elif cmd == "report":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        report.run(days)
    else:
        print(f"Unknown command: {cmd}")

if __name__ == "__main__":
    main()
