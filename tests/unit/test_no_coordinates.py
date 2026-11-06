"""Rule: no element is found or acted on by screen coordinates (works on any screen size/scaling)."""

import re
from pathlib import Path

SRC = Path(__file__).parent.parent.parent / "src"
FORBIDDEN = re.compile(r"click_point|coords\s*=|mouse\.|double_click|from pywinauto import mouse")
# The single documented exception, decided with the user: choosing a row in the selection dialogs.
ALLOWED = {Path("imagetocash/fakturama/row_choice.py")}


def test_source_uses_no_coordinate_apis() -> None:
    offenders = [
        f"{path.relative_to(SRC)}:{n}: {line.strip()}"
        for path in SRC.rglob("*.py")
        if path.relative_to(SRC) not in ALLOWED
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if FORBIDDEN.search(line)
    ]
    assert offenders == []
