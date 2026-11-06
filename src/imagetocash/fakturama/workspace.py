"""Reset the Fakturama workspace to a known clean database, for repeatable test runs.

Never deletes anything: the current database folder is MOVED into a timestamped backup folder and
the clean database is extracted from a Fakturama backup zip (one taken right after first setup:
default settings, VAT 'Tax-free', payment 'Cash', shipping 'Free'; no contacts, products or
documents). A completely empty database is not usable: Fakturama refuses a New Order without a
default shipping method."""

from __future__ import annotations

import contextlib
import shutil
import subprocess
import zipfile
from datetime import datetime
from pathlib import Path

from imagetocash.automation.waiting import WaitTimeout, wait_until
from imagetocash.config import Settings
from imagetocash.fakturama.screen_context import SelectorMap, connect_session

# Prompts Fakturama shows on exit. 'Save Parts' saves open drafts into the database that is about to
# be set aside, which keeps that backup consistent.
_EXIT_ANSWERS = (("Error", "OK"), ("Internal Error", "OK"), ("Quit Fakturama", "Yes"), ("Save Parts", "OK"))


def reset_workspace(settings: Settings, workspace: Path, clean_backup: Path, backups_dir: Path) -> Path:
    """Quit Fakturama, move `workspace/Database` aside, restore `clean_backup`. Returns the folder
    the old database was moved to."""
    if not clean_backup.is_file():
        raise FileNotFoundError(f"clean backup not found: {clean_backup}")
    if _running(settings.fakturama_exe):
        _quit(settings)
    target = backups_dir / datetime.now().strftime("%Y%m%d-%H%M%S")
    target.mkdir(parents=True)
    database = workspace / "Database"
    if database.exists():
        shutil.move(str(database), str(target / "Database"))
    with zipfile.ZipFile(clean_backup) as archive:
        archive.extractall(workspace)
    return target


def _running(exe: Path) -> bool:
    listing = subprocess.run(
        ["tasklist", "/FI", f"IMAGENAME eq {exe.name}"], capture_output=True, text=True, check=False
    ).stdout
    return exe.name.casefold() in listing.casefold()


def _quit(settings: Settings) -> None:
    exe = settings.fakturama_exe
    session = connect_session(settings, SelectorMap.load(settings.selectors_path))
    session.main_wrapper().close()

    def gone() -> bool:
        with contextlib.suppress(Exception):  # windows vanish while the app exits
            for title, button in _EXIT_ANSWERS:
                dialog = next((d for d in session.dialogs() if d.element_info.name == title), None)
                if dialog is not None:
                    pressed = next(
                        b for b in dialog.descendants(control_type="Button") if b.element_info.name == button
                    )
                    pressed.invoke()
        return not _running(exe)

    try:
        wait_until(gone, timeout=60, what=f"{exe.name} to exit", interval=0.5)
    except WaitTimeout as error:
        raise RuntimeError(f"{exe.name} did not exit; close it by hand, nothing was moved") from error
