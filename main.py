import argparse
import asyncio
import os
import signal
import sys
from multiprocessing import Process


def start_api():
    """Flask API サーバーを起動"""
    script_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kanade")

    if os.getenv("ENV") == "production":
        import subprocess

        subprocess.run(
            [
                "gunicorn",
                "--bind",
                "0.0.0.0:5000",
                "--workers",
                "4",
                "--chdir",
                script_dir,
                "app:app",
            ]
        )
    else:
        from kanade.app import app

        app.run(host="0.0.0.0", port=5000, debug=True, use_reloader=False)


def start_worker():
    """BullMQ ワーカーを起動"""
    from kanade.worker import main as worker_main

    asyncio.run(worker_main())


def cmd_serve(_args):
    """serve サブコマンド: API サーバーと BullMQ ワーカーを並行起動"""
    processes: list[Process] = []

    p_api = Process(target=start_api, name="api")
    p_api.start()
    processes.append(p_api)
    print(f"[serve] API server started (pid={p_api.pid})", flush=True)

    p_worker = Process(target=start_worker, name="worker")
    p_worker.start()
    processes.append(p_worker)
    print(f"[serve] BullMQ worker started (pid={p_worker.pid})", flush=True)

    def _shutdown(signum, frame):
        print("\n[serve] Shutting down...")
        for p in processes:
            if p.is_alive():
                p.terminate()
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    for p in processes:
        p.join()


def main():
    parser = argparse.ArgumentParser(
        prog="nagisa",
        description="Nagisa – Apple Music download queue server",
    )
    subparsers = parser.add_subparsers(dest="command")

    # serve
    subparsers.add_parser(
        "serve",
        help="Start the API server and BullMQ worker",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "serve":
        cmd_serve(args)


if __name__ == "__main__":
    main()
