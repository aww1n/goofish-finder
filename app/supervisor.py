import fcntl
import signal
import subprocess
import sys
import time
from pathlib import Path

from redis import Redis

from app.core.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENV_BIN = PROJECT_ROOT / ".venv" / "bin"
RUNTIME_DIR = PROJECT_ROOT / ".run"


def commands() -> dict[str, list[str]]:
    return {
        "worker": [
            str(VENV_BIN / "celery"),
            "-A",
            "app.workers.celery_app:celery_app",
            "worker",
            "--pool=solo",
            "--concurrency=1",
            "--hostname=goofish-worker@%h",
            f"--pidfile={RUNTIME_DIR / 'worker.pid'}",
            "-Q",
            "searches,notifications",
            "-l",
            "INFO",
        ],
        "scheduler": [
            str(VENV_BIN / "celery"),
            "-A",
            "app.workers.celery_app:celery_app",
            "beat",
            f"--pidfile={RUNTIME_DIR / 'scheduler.pid'}",
            f"--schedule={RUNTIME_DIR / 'celerybeat-schedule'}",
            "-l",
            "INFO",
        ],
        "api": [
            str(VENV_BIN / "uvicorn"),
            "app.api.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        "bot": [str(VENV_BIN / "python"), "-m", "app.main"],
    }


def ensure_environment() -> None:
    if not (VENV_BIN / "python").exists():
        raise RuntimeError("Не найдено .venv. Сначала создайте окружение и установите зависимости.")
    try:
        Redis.from_url(get_settings().redis_url, socket_connect_timeout=2, socket_timeout=2).ping()
    except Exception as exc:
        raise RuntimeError("Redis недоступен. Запустите: brew services start redis") from exc


def migrate() -> None:
    print("[supervisor] Применяю миграции…", flush=True)
    subprocess.run(
        [str(VENV_BIN / "alembic"), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        check=True,
    )


def stop_all(processes: dict[str, subprocess.Popen]) -> None:
    print("\n[supervisor] Останавливаю процессы…", flush=True)
    for process in processes.values():
        if process.poll() is None:
            process.terminate()
    deadline = time.monotonic() + 8
    for process in processes.values():
        remaining = max(0, deadline - time.monotonic())
        try:
            process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            process.kill()
    print("[supervisor] Все процессы остановлены.", flush=True)


def main() -> int:
    RUNTIME_DIR.mkdir(exist_ok=True)
    lock_path = RUNTIME_DIR / "supervisor.lock"
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[supervisor] Проект уже запущен другой командой ./run.sh", file=sys.stderr)
            return 1

        try:
            ensure_environment()
            migrate()
        except (RuntimeError, subprocess.CalledProcessError) as exc:
            print(f"[supervisor] Ошибка запуска: {exc}", file=sys.stderr)
            return 1

        processes: dict[str, subprocess.Popen] = {}
        stopping = False

        def request_stop(_signum: int, _frame: object) -> None:
            nonlocal stopping
            stopping = True

        signal.signal(signal.SIGINT, request_stop)
        signal.signal(signal.SIGTERM, request_stop)

        try:
            for name, command in commands().items():
                processes[name] = subprocess.Popen(command, cwd=PROJECT_ROOT)
                print(f"[supervisor] {name} запущен (PID {processes[name].pid})", flush=True)

            print("[supervisor] GOFISH FINDER работает. Для остановки нажмите Ctrl+C.", flush=True)
            while not stopping:
                for name, process in processes.items():
                    code = process.poll()
                    if code is not None:
                        print(
                            f"[supervisor] Процесс {name} завершился с кодом {code}.",
                            file=sys.stderr,
                            flush=True,
                        )
                        stopping = True
                        break
                time.sleep(0.5)
        finally:
            stop_all(processes)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
