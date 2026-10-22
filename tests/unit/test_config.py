import pytest
from pydantic import ValidationError

from pulseops.config import Settings


def test_minimum_interval_depends_on_demo_mode() -> None:
    assert Settings(demo_mode=False).min_interval_seconds == 30
    assert Settings(demo_mode=True).min_interval_seconds == 2


def test_allowed_ports_parsing() -> None:
    assert Settings(allowed_ports="443, 8443").allowed_port_set == {443, 8443}


def test_unknown_timezone_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(display_timezone="Marte/Olympus")
