"""
Intelligence Screening — unified launcher.

Controls:
  R  restart all services
  B  restart backend only
  O  restart bot only
  Q  quit
"""
import subprocess
import sys

def _bootstrap():
    try:
        import rich  # noqa: F401
        return
    except ImportError:
        pass

    candidates = ["py -3.12", "python3.12", "python3", "python"]
    for cmd in candidates:
        parts = cmd.split()
        try:
            result = subprocess.run(
                parts + ["-c", "import rich"],
                capture_output=True,
            )
            if result.returncode == 0:
                subprocess.run(parts + sys.argv)
                sys.exit(0)
        except FileNotFoundError:
            continue

    print("Installing rich...")
    subprocess.run([sys.executable, "-m", "pip", "install", "rich", "--quiet"], check=True)
    import rich  # noqa: F401

_bootstrap()

import msvcrt
import os
import subprocess
import sys
import threading
import time
from collections import deque

import httpx
from dotenv import load_dotenv
from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

load_dotenv()

PYTHON = sys.executable
BACKEND_CMD = [PYTHON, "-m", "uvicorn", "backend.main:app",
               "--host", "127.0.0.1", "--port", "8000"]
BOT_CMD = [PYTHON, "-m", "bot.main"]
HEALTH_URL = "http://127.0.0.1:8000/api/health"
LOG_LINES = 28  # lines visible in each log pane
ALERT_WEBHOOK_URL = os.getenv("ALERT_WEBHOOK_URL", "")


def _fire_alert(message: str):
    if not ALERT_WEBHOOK_URL:
        return
    try:
        httpx.post(ALERT_WEBHOOK_URL, json={"content": message}, timeout=5.0)
    except Exception:
        pass

ASCII_ART = r"""
[bold #818cf8]ooooo                  .oooooo..o                                                     o8o
`888'                 d8P'    `Y8                                                     `"'
 888   .ooooo oo      Y88bo.       .ooooo.  oooo d8b  .ooooo.   .ooooo.  ooo. .oo.   oooo  ooo. .oo.    .oooooooo
 888  d88' `888        `"Y8888o.  d88' `"Y8 `888""8P d88' `88b d88' `88b `888P"Y88b  `888  `888P"Y88b  888' `88b
 888  888   888            `"Y88b 888        888     888ooo888 888ooo888  888   888   888   888   888  888   888
 888  888   888       oo     .d8P 888   .o8  888     888    .o 888    .o  888   888   888   888   888  `88bod8P'
o888o `V8bod888       8""88888P'  `Y8bod8P' d888b    `Y8bod8P' `Y8bod8P' o888o o888o o888o o888o o888o `8oooooo.
            888.                                                                                       d"     YD
            8P'                                                                                        "Y88888P'
            "[/bold #818cf8]
"""

class Service:
    def __init__(self, name: str, cmd: list[str]):
        self.name = name
        self.cmd = cmd
        self.proc: subprocess.Popen | None = None
        self.logs: deque[str] = deque(maxlen=200)
        self.online = False
        self._lock = threading.Lock()

    def start(self):
        with self._lock:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            env = os.environ.copy()
            self.proc = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env,
                cwd=os.path.dirname(__file__),
            )
            self.online = False
        t = threading.Thread(target=self._read_output, daemon=True)
        t.start()

    def stop(self):
        with self._lock:
            if self.proc and self.proc.poll() is None:
                self.proc.terminate()
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.proc.kill()
            self.online = False
            self.proc = None

    def is_running(self) -> bool:
        with self._lock:
            return self.proc is not None and self.proc.poll() is None

    _SUPPRESS = (
        "/api/health",
        "/api/logs/stream",
        "/api/results/flagged",
        "/api/results/stats",
        "/api/config/",
        "/api/questions/",
        "/api/results/?",
        "/favicon.ico",
        "GET /static/",
    )

    def _read_output(self):
        proc = self.proc
        if not proc or not proc.stdout:
            return
        for line in proc.stdout:
            line = line.rstrip("\n\r")
            if not line:
                continue
            if any(s in line for s in self._SUPPRESS):
                continue
            with self._lock:
                self.logs.append(line)

    def log_panel(self) -> Panel:
        dot_color = "#3ddc84" if self.online else ("#f59e0b" if self.is_running() else "#ff6464")
        dot = f"[{dot_color}]●[/{dot_color}]"
        status_word = "ONLINE" if self.online else ("STARTING" if self.is_running() else "OFFLINE")
        status_color = "#3ddc84" if self.online else ("#f59e0b" if self.is_running() else "#ff6464")
        title = f"{dot} [bold]{self.name}[/bold]  [{status_color}]{status_word}[/{status_color}]"

        lines = list(self.logs)[-LOG_LINES:]
        text = Text()
        for line in lines:
            lo = line.lower()
            if "error" in lo or "critical" in lo or "exception" in lo or "traceback" in lo:
                text.append(line + "\n", style="#ff6464")
            elif "warning" in lo or "warn" in lo:
                text.append(line + "\n", style="#f59e0b")
            elif "info" in lo or "started" in lo or "ready" in lo or "loaded" in lo:
                text.append(line + "\n", style="#d4d4e0")
            else:
                text.append(line + "\n", style="#4a4a5a")

        return Panel(
            text,
            title=title,
            title_align="left",
            border_style="#1e1e2a",
            padding=(0, 1),
        )


backend_svc = Service("BACKEND", BACKEND_CMD)
bot_svc = Service("BOT", BOT_CMD)

_running = True
_startup_done = False


def _health_loop():
    global _startup_done
    was_online = False
    while _running:
        try:
            r = httpx.get(HEALTH_URL, timeout=2.0)
            backend_svc.online = r.status_code == 200
        except Exception:
            backend_svc.online = False
        bot_svc.online = bot_svc.is_running()

        if not _startup_done and backend_svc.online and bot_svc.online:
            _startup_done = True

        if was_online and not backend_svc.online:
            _fire_alert("Backend went offline unexpectedly. The launcher is still running and will keep polling.")
        was_online = backend_svc.online

        time.sleep(3)


def _make_layout(console: Console) -> Table:
    controls = Text()
    controls.append("  [R]", style="bold #818cf8")
    controls.append(" Restart All  ", style="#64647a")
    controls.append("[B]", style="bold #818cf8")
    controls.append(" Backend  ", style="#64647a")
    controls.append("[O]", style="bold #818cf8")
    controls.append(" Bot  ", style="#64647a")
    controls.append("[Q]", style="bold #ff6464")
    controls.append(" Quit  ", style="#64647a")

    left = backend_svc.log_panel()
    right = bot_svc.log_panel()

    root = Table.grid(expand=True)
    root.add_row(Text.from_markup(ASCII_ART))
    root.add_row(Columns([left, right], expand=True))
    root.add_row(Panel(controls, border_style="#1e1e2a", padding=(0, 0)))
    return root


def _handle_key(key: bytes):
    k = key.lower()
    if k == b"q":
        global _running
        _running = False
    elif k == b"r":
        backend_svc.logs.append(">>> Restarting backend...")
        bot_svc.logs.append(">>> Restarting bot...")
        backend_svc.start()
        bot_svc.start()
    elif k == b"b":
        backend_svc.logs.append(">>> Restarting backend...")
        backend_svc.start()
    elif k == b"o":
        bot_svc.logs.append(">>> Restarting bot...")
        bot_svc.start()


def main():
    global _running

    console = Console()

    backend_svc.logs.append(">>> Starting backend...")
    bot_svc.logs.append(">>> Starting bot...")
    backend_svc.start()
    bot_svc.start()

    health_thread = threading.Thread(target=_health_loop, daemon=True)
    health_thread.start()

    with Live(
        _make_layout(console),
        console=console,
        refresh_per_second=30,
        screen=True,
    ) as live:
        while _running:
            if msvcrt.kbhit():
                key = msvcrt.getch()
                if key in (b"\x00", b"\xe0"):
                    msvcrt.getch()  # consume extended key second byte
                else:
                    _handle_key(key)

            live.update(_make_layout(console))
            time.sleep(1 / 240)

    backend_svc.stop()
    bot_svc.stop()
    console.print("\n[#64647a]Stopped.[/#64647a]")


if __name__ == "__main__":
    main()
