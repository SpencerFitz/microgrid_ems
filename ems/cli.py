import argparse
import json
from pathlib import Path
import platform
import sqlite3
import sys

from .config import load_config


ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    parser = argparse.ArgumentParser(description="EMS Python/Windows simulation bootstrap")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/site/demo.json")
    parser.add_argument("--data-dir", type=Path, default=ROOT / "runtime")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check Python/Windows/SQLite without writing data")
    commands.add_parser("validate", help="validate configuration without starting")
    commands.add_parser("demo", help="run two short lifecycle sessions and verify retention")
    commands.add_parser("demo-contracts", help="validate static domain fixtures and explain OFFLINE quality")
    commands.add_parser("demo-simulator", help="verify power balance, SOC and communication recovery using virtual time")
    sim_parser = commands.add_parser("simulate", help="evaluate one scenario with virtual time; no polling")
    sim_parser.add_argument("--scenario", type=Path, default=ROOT / "configs/scenarios/demo.json")
    sim_parser.add_argument("--seconds", type=float, default=0, help="virtual elapsed seconds, default 0")
    commands.add_parser("status", help="inspect recorded heartbeat and live instance lock")
    run_parser = commands.add_parser("run", help="foreground runtime; Ctrl+C to stop")
    run_parser.add_argument("--ticks", type=int, default=0, help="0 runs until Ctrl+C")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 12) or sys.platform != "win32":
        print(json.dumps({"error": "requires Python >= 3.12 on Windows"}), file=sys.stderr)
        return 1
    try:
        if args.command == "doctor":
            result = {"status": "READY_M01", "python": platform.python_version(),
                      "platform": platform.platform(), "sqlite": sqlite3.sqlite_version,
                      "externalServicesRequired": False, "guiChecked": False}
        elif args.command == "demo-simulator":
            from .simulator.demo import demo_simulator
            result = demo_simulator(ROOT)
        elif args.command == "simulate":
            from .simulator.demo import simulate_scenario
            result = simulate_scenario(args.scenario, args.seconds)
        elif args.command == "demo-contracts":
            from .domain.demo import demo_contracts
            result = demo_contracts(ROOT)
        elif args.command == "validate":
            config = load_config(args.config)
            result = {"status": "VALID", "siteId": config.site_id, "configVersion": config.config_version}
        else:
            from .runtime import demo, read_status, run
            if args.command == "status":
                result = read_status(args.data_dir)
            else:
                config = load_config(args.config)
                result = demo(config, args.data_dir) if args.command == "demo" else run(config, args.data_dir, ticks=args.ticks)
        print(json.dumps(result, ensure_ascii=False))
        if args.command == "status" and result["state"] == "UNAVAILABLE":
            return 1
        return 0
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        # Never dump configuration, environment variables or credentials.
        print(json.dumps({"error": str(exc), "type": type(exc).__name__}, ensure_ascii=False), file=sys.stderr)
        return 1
