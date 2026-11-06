"""Dropdown search: type letters until the combo shows the option, then one arrow away and back."""

from imagetocash.automation.input import arrow_nudge, type_until_shown


class FakeCombo:
    """Windows combo prefix search: the first option starting with the typed text (case-insensitive)."""

    def __init__(self, options: list[str]) -> None:
        self.options, self.prefix, self.keys = options, "", []
        self.shown = options[0]

    def send(self, keys: str) -> None:
        self.keys.append(keys)
        self.prefix += keys[1:-1] if keys.startswith("{") else keys
        hit = next((o for o in self.options if o.casefold().startswith(self.prefix.casefold())), None)
        if hit is not None:
            self.shown = hit


def test_one_letter_is_enough_when_it_lands_on_the_target() -> None:
    combo = FakeCombo(["Afghanistan", "Germany", "Japan"])
    assert type_until_shown(combo.send, lambda: combo.shown, "Germany")
    assert combo.keys == ["G"]


def test_shared_prefix_types_more_letters() -> None:
    combo = FakeCombo(["Gabon", "Georgia", "Germany", "Ghana"])
    assert type_until_shown(combo.send, lambda: combo.shown, "Germany")
    assert combo.keys == ["G", "e", "r"]  # Gabon, Georgia, Germany


def test_spaces_and_send_keys_specials_are_typed_literally() -> None:
    combo = FakeCombo(["VAT 19", "VAT 19%"])
    assert type_until_shown(combo.send, lambda: combo.shown, "VAT 19%")
    assert combo.keys == ["V", "A", "T", " ", "1", "9", "{%}"]  # '%' is Alt for send_keys: braced


def test_never_shown_returns_false() -> None:
    combo = FakeCombo(["Net", "Gross"])
    assert not type_until_shown(combo.send, lambda: "Gross", "Net")


def test_nudge_ends_on_the_target_with_an_arrow_key() -> None:
    assert arrow_nudge(0, 5) == "{DOWN}{UP}"
    assert arrow_nudge(2, 5) == "{DOWN}{UP}"
    assert arrow_nudge(4, 5) == "{UP}{DOWN}"  # last option: away is Up
    assert arrow_nudge(0, 1) == ""  # nothing to move to
