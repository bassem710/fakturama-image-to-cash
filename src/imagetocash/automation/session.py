"""Launch or attach to the desktop app through Microsoft UI Automation (pywinauto, backend="uia")."""

from __future__ import annotations

import ctypes
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pywinauto import Application

from imagetocash.automation.waiting import wait_until

SW_MAXIMIZE = 3
_user32 = ctypes.windll.user32


@dataclass
class DesktopSession:
    """One running app, addressed by its main window HANDLE.

    Criteria lookups (title_re / class_name) silently miss a minimized SWT window, so the
    main window is located once by class through Application.windows() and then by handle.
    """

    app: Application
    main_handle: int
    error_dialog_title: str = ""  # the app's own failure dialog: seeing it stops the run

    @classmethod
    def attach_or_launch(
        cls,
        exe_path: Path,
        *,
        main_window_class: str,
        main_title_prefix: str,
        error_dialog_title: str = "",
        timeout: float = 120.0,
    ) -> DesktopSession:
        app = Application(backend="uia")
        try:
            app.connect(path=exe_path.name, timeout=2)
        except Exception:
            subprocess.Popen([str(exe_path)], cwd=str(exe_path.parent))
            wait_until(
                lambda: _try_connect(app, exe_path.name),
                timeout=timeout,
                what=f"{exe_path.name} to start",
                interval=0.25,
            )

        def main_handle() -> int | None:
            for window in app.windows():
                info = window.element_info
                if info.class_name == main_window_class and info.name.startswith(main_title_prefix):
                    return int(window.handle)
            return None

        handle = wait_until(main_handle, timeout=timeout, what="the main window", interval=0.25)
        return cls(app=app, main_handle=handle, error_dialog_title=error_dialog_title)

    def main_window(self) -> Any:
        """WindowSpecification of the main window (supports child_window(...))."""
        return self.app.window(handle=self.main_handle)

    def main_wrapper(self) -> Any:
        return self.main_window().wrapper_object()

    def bring_to_front(self) -> None:
        """Maximized and in front. Cheap when it already is (two Win32 calls, no UIA)."""
        if _user32.GetForegroundWindow() == self.main_handle and _user32.IsZoomed(self.main_handle):
            return
        if _user32.IsIconic(self.main_handle):
            _user32.ShowWindow(self.main_handle, SW_MAXIMIZE)
        wrapper = self.main_wrapper()
        if not wrapper.is_maximized():
            wrapper.maximize()
        wrapper.set_focus()

    def dialogs(self) -> list[Any]:
        """Every window of the app other than the main one: top-level dialogs AND owned child windows."""
        found = [w for w in self.app.windows() if int(w.handle) != self.main_handle]
        found += [c for c in self.main_wrapper().children() if c.element_info.control_type == "Window"]
        return found

    def wait_for_dialog(self, title: str, timeout: float) -> Any:
        def probe() -> Any:
            return next((d for d in self.dialogs() if d.element_info.name == title), None)

        return wait_until(probe, timeout=timeout, what=f"dialog '{title}'")

    def raise_if_app_error(self) -> None:
        """The app reports internal failures in its own error dialog: stop, never click on."""
        if self.error_dialog_title and any(d.element_info.name == self.error_dialog_title for d in self.dialogs()):
            raise AppInternalError(f"the app showed its {self.error_dialog_title!r} dialog")

    def wait_for_dialog_closed(self, title: str, timeout: float) -> None:
        self.raise_if_app_error()
        wait_until(
            lambda: all(d.element_info.name != title for d in self.dialogs()),
            timeout=timeout,
            what=f"dialog '{title}' to close",
        )


class AppInternalError(RuntimeError):
    pass


def _try_connect(app: Application, exe_name: str) -> bool:
    try:
        app.connect(path=exe_name, timeout=1)
        return True
    except Exception:
        return False
