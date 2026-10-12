from pathlib import PureWindowsPath

import pytest

from lattice.docs.mkdocs_web import _is_light, normalize_hex_color, page_source_key


def test_page_source_key_uses_forward_slashes_on_windows_paths():
    # MkDocs's page.file.src_uri always uses forward slashes, so the page-to-schema map must
    # too, or the lookup in LatticePlugin.on_page_markdown misses on Windows.
    content_directory = PureWindowsPath("C:/project/docs")
    output_path = PureWindowsPath("C:/project/docs/specifications/RS0003.md")
    assert page_source_key(output_path, content_directory) == "specifications/RS0003.md"


@pytest.mark.parametrize(
    ("color", "expected"),
    [("#fff", "#ffffff"), ("#2C358e", "#2C358e"), ("#9e9e9e", "#9e9e9e"), ("#a1b", "#aa11bb")],
)
def test_normalize_hex_color_expands_shorthand_to_six_digits(color, expected):
    assert normalize_hex_color(color) == expected


@pytest.mark.parametrize("color", ["#abcd", "#ffffff80", "#ggg", "#"])
def test_normalize_hex_color_rejects_anything_but_three_or_six_hex_digits(color):
    with pytest.raises(ValueError, match="3- or 6-digit hex"):
        normalize_hex_color(color)


def test_a_shorthand_color_can_be_classified_as_light_or_dark():
    assert _is_light(normalize_hex_color("#fff"))
    assert not _is_light(normalize_hex_color("#000"))
