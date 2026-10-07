from pathlib import PureWindowsPath

from lattice.docs.mkdocs_web import page_source_key


def test_page_source_key_uses_forward_slashes_on_windows_paths():
    # MkDocs's page.file.src_uri always uses forward slashes, so the page-to-schema map must
    # too, or the lookup in LatticePlugin.on_page_markdown misses on Windows.
    content_directory = PureWindowsPath("C:/project/docs")
    output_path = PureWindowsPath("C:/project/docs/specifications/RS0003.md")
    assert page_source_key(output_path, content_directory) == "specifications/RS0003.md"
