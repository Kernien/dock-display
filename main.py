import asyncio
import glob
import json
import os
import pwd
import re

# The decky plugin module is located at decky-loader/plugin
import decky

DRM_DIR = "/sys/class/drm"
# Connectors that belong to the built-in screen (or are not real outputs).
INTERNAL_PREFIXES = ("eDP", "LVDS", "DSI", "Writeback")
SETTINGS_FILE = os.path.join(decky.DECKY_PLUGIN_SETTINGS_DIR, "settings.json")
DEFAULT_SETTINGS = {"external_enabled": True, "confirm_external": True}
# Seconds the user has to confirm the external display before falling back to the Deck screen.
CONFIRM_TIMEOUT = 15
# While switching to the external display the internal screen is kept asleep until the
# external output has stayed up for STABLE_SECONDS, but never longer than SWITCH_TIMEOUT.
STABLE_SECONDS = 4
SWITCH_TIMEOUT = 15


def external_connectors() -> list[str]:
    """Paths of external DRM connectors, e.g. /sys/class/drm/card0-DP-1."""
    result = []
    for path in sorted(glob.glob(os.path.join(DRM_DIR, "card*-*"))):
        match = re.match(r"^card\d+-(.+)$", os.path.basename(path))
        if not match or match.group(1).startswith(INTERNAL_PREFIXES):
            continue
        if os.path.isfile(os.path.join(path, "status")):
            result.append(path)
    return result


def write_status(connector: str, value: str) -> None:
    # "off" forces the kernel to report the connector as disconnected,
    # "detect" returns it to normal hotplug detection.
    with open(os.path.join(connector, "status"), "w") as f:
        f.write(value)


def read_status(connector: str) -> str:
    try:
        with open(os.path.join(connector, "status")) as f:
            return f.read().strip()
    except OSError:
        return "unknown"


def load_settings() -> dict:
    try:
        with open(SETTINGS_FILE) as f:
            return {**DEFAULT_SETTINGS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict) -> None:
    os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f)


def user_runtime_dir() -> str:
    return f"/run/user/{pwd.getpwnam(decky.DECKY_USER).pw_uid}"


async def gamescope_ready(timeout: float) -> bool:
    socket = os.path.join(user_runtime_dir(), "gamescope-0")
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not os.path.exists(socket):
        if loop.time() >= deadline:
            return False
        await asyncio.sleep(1)
    return True


async def gamescopectl(*args: str) -> str:
    # Decky runs from a PyInstaller bundle, so its LD_LIBRARY_PATH must not leak into system tools.
    env = {
        "PATH": "/usr/bin:/bin",
        "XDG_RUNTIME_DIR": user_runtime_dir(),
        "GAMESCOPE_WAYLAND_DISPLAY": "gamescope-0",
    }
    try:
        proc = await asyncio.create_subprocess_exec(
            "runuser", "-u", decky.DECKY_USER, "--", "gamescopectl", *args,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
        if proc.returncode != 0:
            decky.logger.error(f"gamescopectl {args} failed ({proc.returncode}): {stderr.decode().strip()}")
        return stdout.decode()
    except (OSError, asyncio.TimeoutError) as e:
        decky.logger.error(f"gamescopectl {args} error: {e}")
        return ""


async def gamescope_repoll() -> None:
    """Ask gamescope to re-scan outputs; it does not react to a forced "off" on its own."""
    await gamescopectl("backend_set_dirty")


def external_active() -> bool:
    """True when the kernel reports a picture being sent to an external connector."""
    for connector in external_connectors():
        try:
            with open(os.path.join(connector, "enabled")) as f:
                if f.read().strip() == "enabled":
                    return True
        except OSError:
            pass
    return False


async def wait_for_stable_external(stable: float, timeout: float) -> bool:
    """Wait until the external output has stayed active for `stable` seconds in a row."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    active_since = None
    while loop.time() < deadline:
        if external_active():
            active_since = active_since or loop.time()
            if loop.time() - active_since >= stable:
                return True
        else:
            active_since = None
        await asyncio.sleep(0.1)
    return external_active()


class Plugin:
    async def get_state(self) -> dict:
        return {
            "externalEnabled": self.settings["external_enabled"],
            "confirmExternal": self.settings["confirm_external"],
            "pendingConfirm": self.revert_task is not None,
            "confirmTimeout": CONFIRM_TIMEOUT,
            "connectors": [
                {"name": os.path.basename(c).split("-", 1)[1], "status": read_status(c)}
                for c in external_connectors()
            ],
        }

    async def set_external_enabled(self, enabled: bool) -> dict:
        async with self.lock:
            self._cancel_revert()
            self.settings["external_enabled"] = enabled
            save_settings(self.settings)
            switched = await self._apply(enabled)
            if switched and self.settings["confirm_external"]:
                self.revert_task = asyncio.create_task(self._revert_after_timeout())
        return await self.get_state()

    async def confirm_external(self) -> dict:
        self._cancel_revert()
        return await self.get_state()

    async def set_confirm_external(self, confirm: bool) -> dict:
        self.settings["confirm_external"] = confirm
        save_settings(self.settings)
        return await self.get_state()

    def _cancel_revert(self) -> None:
        if self.revert_task is not None:
            self.revert_task.cancel()
            self.revert_task = None

    async def _revert_after_timeout(self) -> None:
        await asyncio.sleep(CONFIRM_TIMEOUT)
        async with self.lock:
            self.revert_task = None
            decky.logger.info("External display not confirmed, returning to the Deck screen")
            self.settings["external_enabled"] = False
            save_settings(self.settings)
            await self._apply(False)
        await decky.emit("external_reverted")

    async def _apply(self, enabled: bool, settle: bool = True) -> bool:
        """Returns True when the picture moved to an external display."""
        connectors = external_connectors()
        value = "detect" if enabled else "off"
        for connector in connectors:
            try:
                write_status(connector, value)
            except OSError as e:
                decky.logger.error(f"Cannot write {value} to {connector}: {e}")
        decky.logger.info(f"External output {'enabled' if enabled else 'disabled'}: {connectors}")
        if not enabled or not settle:
            await gamescope_repoll()
            return False
        if not any(read_status(c) == "connected" for c in connectors):
            return False
        # A monitor woken from standby (or the dock's DP-HDMI bridge) usually drops and
        # re-raises hotplug a couple of times, and gamescope falls back to the internal
        # screen for each drop. Keep the internal screen asleep until the link settles,
        # so those fallbacks are not seen as flicker on the Deck.
        started = asyncio.get_running_loop().time()
        await gamescopectl("drm_sleep_internal_screen", "1")
        try:
            await gamescope_repoll()
            stable = await wait_for_stable_external(stable=STABLE_SECONDS, timeout=SWITCH_TIMEOUT)
        finally:
            await gamescopectl("drm_sleep_internal_screen", "0")
        elapsed = asyncio.get_running_loop().time() - started
        decky.logger.info(f"External output {'settled' if stable else 'did not settle'} in {elapsed:.1f}s")
        return stable

    async def _main(self):
        self.lock = asyncio.Lock()
        self.revert_task = None
        self.settings = load_settings()
        if not self.settings["external_enabled"]:
            # On boot gamescope may start after us; wait for it before re-polling.
            if await gamescope_ready(timeout=120):
                await asyncio.sleep(2)
            async with self.lock:
                await self._apply(False)

    async def _unload(self):
        # Never leave the monitor forced off while the plugin is not running.
        # Settings stay as they are, so the choice is re-applied on next load.
        self._cancel_revert()
        if not self.settings["external_enabled"]:
            await self._apply(True, settle=False)

    async def _uninstall(self):
        await self._apply(True, settle=False)
