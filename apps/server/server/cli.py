"""Operator commands. Passwords are accepted only from the terminal or stdin."""
import argparse
import getpass
import sys

from .common import Fault
from .config import Settings
from .repository import Repository
from .security import Security


def main():
    parser = argparse.ArgumentParser(prog="python -m server.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    account = commands.add_parser("create-account")
    account.add_argument("--login", required=True)
    account.add_argument("--display-name", required=True)
    account.add_argument("--password-stdin", action="store_true")
    password_command = commands.add_parser("set-password")
    password_command.add_argument("--login", required=True)
    password_command.add_argument("--password-stdin", action="store_true")
    commands.add_parser("migrate")
    backup = commands.add_parser("backup")
    backup.add_argument("destination")
    args = parser.parse_args()
    repo = None
    try:
        settings = Settings.from_env()
        repo = Repository(settings.database)
        if args.command in {"create-account", "set-password"}:
            password = sys.stdin.readline(4098).rstrip("\r\n") if args.password_stdin else getpass.getpass("Account password: ")
            security = Security(repo, settings)
            if args.command == "create-account":
                security.create_account(args.login, password, args.display_name)
                print("Account created")
            else:
                security.set_password(args.login, password)
                print("Password updated; browser sessions invalidated")
        elif args.command == "backup":
            repo.backup(args.destination)
            print("Consistent backup created")
        else:
            repo.migrate()
            print("Schema is current")
        return 0
    except (Fault, OSError, ValueError, RuntimeError):
        print("Operation failed; check account input, configuration and file permissions", file=sys.stderr)
        return 1
    finally:
        if repo:
            repo.close()


if __name__ == "__main__":
    raise SystemExit(main())
