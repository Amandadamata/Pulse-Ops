import pytest

from pulseops.domain.status_codes import parse_status_codes


def test_ranges_and_single_codes() -> None:
    accepted = parse_status_codes("200-299, 301")
    assert 200 in accepted and 299 in accepted and 301 in accepted
    assert 300 not in accepted and 500 not in accepted
    assert str(accepted) == "200-299,301"


@pytest.mark.parametrize(
    "spec", ["", "abc", "299-200", "99", "600", "200-", "-200", "200,,201", "1" * 101]
)
def test_invalid_specs_are_rejected(spec: str) -> None:
    with pytest.raises(ValueError):
        parse_status_codes(spec)
