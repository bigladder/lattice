from pathlib import PureWindowsPath

import pytest

from lattice.docs.mkdocs_web import (
    _is_light,
    copy_extra_pages,
    find_license_file,
    footer_copyright,
    normalize_hex_color,
    page_source_key,
    site_plugins,
)


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


def test_extra_pages_become_nav_entries_in_file_name_order(tmp_path):
    source = tmp_path / "web" / "extra-pages"
    (source / "assets").mkdir(parents=True)
    (source / "b-mapping.md").write_text("# Mapping\n")
    (source / "a-changelog.md").write_text("# Changelog\n")
    (source / "assets" / "figure.png").write_bytes(b"")
    content = tmp_path / "docs"

    assert copy_extra_pages(source, content) == ["extra-pages/a-changelog.md", "extra-pages/b-mapping.md"]
    # Assets come along, so a page's relative image links still resolve.
    assert (content / "extra-pages" / "assets" / "figure.png").exists()


def test_a_page_removed_from_extra_pages_is_not_built_from_a_stale_copy(tmp_path):
    source = tmp_path / "extra-pages"
    source.mkdir()
    (source / "old.md").write_text("# Old\n")
    content = tmp_path / "docs"
    copy_extra_pages(source, content)

    (source / "old.md").unlink()
    (source / "new.md").write_text("# New\n")

    assert copy_extra_pages(source, content) == ["extra-pages/new.md"]
    assert not (content / "extra-pages" / "old.md").exists()


def test_an_extra_page_can_be_a_jinja_template(tmp_path):
    source = tmp_path / "extra-pages"
    source.mkdir()
    (source / "_footer.md").write_text("Included footer.\n")
    (source / "rendered.md.j2").write_text("# Rendered\n\n{{ 2 + 3 }}\n\n{% include '_footer.md' %}\n")
    content = tmp_path / "docs"

    nav = copy_extra_pages(source, content)

    rendered = (content / "extra-pages" / "rendered.md").read_text()
    assert "5" in rendered
    assert "Included footer." in rendered
    # Only the rendered output is published -- not the template source, and not the partial it
    # includes, which would otherwise show up as a page of its own.
    assert not (content / "extra-pages" / "rendered.md.j2").exists()
    assert not (content / "extra-pages" / "_footer.md").exists()
    assert nav == ["extra-pages/rendered.md"]


def test_a_configured_copyright_is_used_as_written():
    notice = "Copyright (c) IBPSA-USA. Licensed under BSD-3-Clause."
    assert footer_copyright(notice, "IBPSA-USA", 2026, "https://example.com/LICENSE") == notice


def test_the_default_footer_links_to_the_license_instead_of_reserving_all_rights():
    footer = footer_copyright(None, "IBPSA-USA", 2026, "https://github.com/o/r/blob/HEAD/LICENSE.txt")
    assert footer == '&copy; 2026 IBPSA-USA &middot; <a href="https://github.com/o/r/blob/HEAD/LICENSE.txt">License</a>'
    assert "All rights reserved" not in footer


def test_without_a_license_file_the_default_footer_credits_only_the_author():
    assert footer_copyright(None, "IBPSA-USA", 2026) == "&copy; 2026 IBPSA-USA"


def test_a_license_file_is_found_under_any_of_its_common_names(tmp_path):
    assert find_license_file(tmp_path) is None
    (tmp_path / "LICENSE.txt").write_text("BSD-3-Clause\n")
    assert find_license_file(tmp_path) == tmp_path / "LICENSE.txt"


def test_the_print_page_is_off_unless_configured():
    assert "print-site" not in site_plugins("/project")


def test_a_configured_print_page_adds_the_print_site_plugin_last():
    assert site_plugins("/project", print_page=True)[-1] == "print-site"


def test_a_project_without_extra_pages_adds_no_nav_entries(tmp_path):
    assert copy_extra_pages(tmp_path / "missing", tmp_path / "docs") == []
