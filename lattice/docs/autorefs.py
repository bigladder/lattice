"""
Auto-links every mention of a Data Group or Enumeration name back to its own section -- both
inline, as each table cell is built (see `link_mentions`, used by schema_table.py), and across
hand-written prose elsewhere on a page (see `link_prose_mentions`, run as an mkdocs
`on_page_markdown` hook). Cross-page resolution (a name mentioned on one specification page but
defined on another) is left to the mkdocs-autorefs plugin: both functions emit ordinary
reference-style links ("[`Name`][scope:name]"; see grid_table.scoped_anchor_id for the id), and
autorefs resolves each one to wherever that id's heading actually landed.
"""

import re
from pathlib import Path

from ..file_io import get_file_basename, load
from .grid_table import scoped_anchor_id


def _schema_files(schema_dir):
    schema_dir = Path(schema_dir)
    if not schema_dir.exists():
        return []
    return sorted(
        path
        for path in schema_dir.iterdir()
        if path.is_file() and (path.name.endswith(".schema.yaml") or path.name.endswith(".schema.yml"))
    )


def _data_group_and_enumeration_names(schema_data):
    """
    - schema_data: dict, a loaded *.schema.yaml file's contents
    RETURN: set of string, the name of every Data Group and Enumeration defined at the top level
    of `schema_data`. A lighter-weight stand-in for schema_table.load_structure_from_object here
    (which this module can't import without a circular dependency: schema_table.py itself calls
    into link_mentions below) -- only the names are needed, not the fully-rendered table data.
    """
    return {
        name
        for name, obj in schema_data.items()
        if isinstance(obj, dict) and obj.get("Object Type") in ("Data Group", "Enumeration")
    }


class ReferenceIndex:
    """
    A project-wide map from Data Group/Enumeration name to where it's defined.

    A name may be defined independently in more than one schema file -- e.g. several
    Representation Specifications each conventionally define their own "Description" Data
    Group -- so resolving one correctly requires knowing which schema source is asking:
    `resolve` prefers a same-source definition over a project-wide one. A name defined in exactly
    one schema file resolves the same way regardless of which source asks.
    """

    def __init__(self, schema_dir):
        by_source: dict[str, dict[str, str]] = {}
        occurrences: dict[str, int] = {}
        for path in _schema_files(schema_dir):
            source = get_file_basename(path, depth=2)
            names = _data_group_and_enumeration_names(load(path))
            by_source[source] = {name: scoped_anchor_id(name, source) for name in names}
            for name in names:
                occurrences[name] = occurrences.get(name, 0) + 1
        self._by_source = by_source
        self._unambiguous = {
            name: slug for names in by_source.values() for name, slug in names.items() if occurrences[name] == 1
        }
        self._unambiguous_source = {
            name: candidate_source
            for candidate_source, names in by_source.items()
            for name in names
            if occurrences[name] == 1
        }
        self._mention_pattern = None

    def resolve(self, name, source=None):
        """
        - name: string, a Data Group or Enumeration name
        - source: None or string, the schema source of the text being scanned
        RETURN: None or string, the anchor id to link `name` to, if resolvable unambiguously --
        a same-source definition first, else a project-wide definition that isn't defined more
        than once anywhere. None if neither applies (an ambiguous name mentioned from a source
        that doesn't itself define it).
        """
        if source is not None and name in self._by_source.get(source, {}):
            return self._by_source[source][name]
        return self._unambiguous.get(name)

    def source_of(self, name, source=None):
        """
        - name: string, a Data Group or Enumeration name
        - source: None or string, the schema source of the text being scanned
        RETURN: None or string, the schema source (e.g. "RS0003") that defines `name`, resolved
        with the same precedence as resolve() -- so a caller that also needs to know which
        specification page a cross-referenced name lives on (e.g. to build a link to it; see
        link_diagram_nodes) can get both from the same lookup rule.
        """
        if source is not None and name in self._by_source.get(source, {}):
            return source
        return self._unambiguous_source.get(name)

    def names(self):
        """RETURN: set of string, every Data Group/Enumeration name known project-wide."""
        return set(self._unambiguous) | {name for names in self._by_source.values() for name in names}

    def mention_pattern(self):
        """RETURN: compiled regex, matching any known name as a whole word (longest names first,
        so one name that's a prefix of another -- e.g. "Performance" vs. "PerformanceMap" --
        doesn't shadow the longer match)."""
        if self._mention_pattern is None:
            names = self.names()
            body = "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True)) if names else r"(?!)"
            self._mention_pattern = re.compile(rf"\b({body})\b")
        return self._mention_pattern


# Matches whatever a mention must never be inserted into: a fenced code block, an inline code
# span, or an existing link (inline or reference-style). Wrapped in one capturing group so
# `re.split` keeps these spans in its result instead of discarding them.
_CODE_OR_LINK_SPAN = re.compile(r"(```[\s\S]*?```|`[^`]*`|\[[^\]]+\]\([^)]+\)|\[[^\]]+\]\[[^\]]*\])")


def link_mentions(text, reference_index, source=None):
    """
    - text: string, a single cell's Markdown content (e.g. a Description, Notes, or Type value)
    - reference_index: ReferenceIndex
    - source: None or string, the schema source `text` came from
    RETURN: string, `text` with every exact mention of a known Data Group/Enumeration name
    wrapped as a monospace autoref link (e.g. "[`Name`][scope:name]"), except inside an existing
    code span, fenced block, or link. This links a Data Group/Enumeration's own name within its
    own table too (e.g. a recursive Data Group mentioning itself) -- harmless, and keeps every
    mention styled the same way.
    """
    mention_pattern = reference_index.mention_pattern()

    def replace(match):
        name = match.group(1)
        anchor = reference_index.resolve(name, source)
        return f"[`{name}`][{anchor}]" if anchor is not None else name

    return "".join(
        chunk if _CODE_OR_LINK_SPAN.fullmatch(chunk) else mention_pattern.sub(replace, chunk)
        for chunk in _CODE_OR_LINK_SPAN.split(text)
    )


# A generated grid table's own lines (borders and cell rows both start with "|" or "+") are
# already linked inline (see link_mentions above, called from schema_table.create_table_from_list)
# -- touching them again here would insert text into a cell padded to an exact fixed width,
# breaking the table's column alignment. This lets link_prose_mentions recognize and skip them.
_GRID_TABLE_LINE = re.compile(r"^[ \t]*[|+]")

# A Markdown heading (see schema_table.write_header) -- left untouched entirely, rather than
# linking words within the heading's own text.
_HEADING_LINE = re.compile(r"^#{1,6}[ \t]")

# A reference-style link's target definition, e.g. '[1]: assets/BuildingPerformanceOutputReport
# .schema.json' (see MkDocsWeb.make_schema_page/make_examples_page) -- a line-level construct
# distinct from the inline "[text][1]" links _CODE_OR_LINK_SPAN already protects. A name mentioned
# inside a file path here is part of the target, not prose to link.
_LINK_DEFINITION_LINE = re.compile(r"^[ \t]*\[[^\]]+\]:")


def link_prose_mentions(markdown_text, reference_index, source=None):
    """
    - markdown_text: string, one page's full Markdown source, before mkdocs renders it
    - reference_index: ReferenceIndex
    - source: None or string, the schema source this page corresponds to (see
      MkDocsWeb.page_source_map), used to prefer a same-source Data Group/Enumeration definition
      over an unrelated project-wide one of the same name
    RETURN: string, `markdown_text` with every exact mention of a known Data Group/Enumeration
    name -- outside of Lattice's own generated grid tables, which are already linked inline as
    they're built (see link_mentions) -- wrapped as a monospace autoref link. Skips fenced code
    blocks, inline code spans, existing links, and heading lines themselves.
    """
    mention_pattern = reference_index.mention_pattern()

    def process_line(line):
        if _HEADING_LINE.match(line) or _GRID_TABLE_LINE.match(line) or _LINK_DEFINITION_LINE.match(line):
            return line

        def replace(match):
            name = match.group(1)
            anchor = reference_index.resolve(name, source)
            return f"[`{name}`][{anchor}]" if anchor is not None else name

        return mention_pattern.sub(replace, line)

    def process_chunk(chunk):
        lines = chunk.splitlines(keepends=True)
        return "".join(process_line(line) for line in lines)

    return "".join(
        chunk if _CODE_OR_LINK_SPAN.fullmatch(chunk) else process_chunk(chunk)
        for chunk in _CODE_OR_LINK_SPAN.split(markdown_text)
    )


# A ```mermaid flowchart block as diagram.render_tree emits it, and one of its node-definition
# lines -- either a root ("    n_Foo[\"Foo\"]") or a child ("    n_Foo --> n_Foo_Bar[\"Bar\"]");
# a cycle back-edge (diagram._emit_node's "recursive_target_path" case) has no ["label"] and so
# never matches, since there's no new node there to link.
_MERMAID_BLOCK = re.compile(r"```mermaid\n(.*?)\n```", re.DOTALL)
_MERMAID_NODE_LINE = re.compile(r'^ {4}(?:\S+ --> )?(n_\S+)\["([^"]*)"\]$', re.MULTILINE)


def link_diagram_nodes(markdown_text, reference_index, source=None):
    """
    - markdown_text: string, one page's full Markdown source, before mkdocs renders it
    - reference_index: ReferenceIndex
    - source: None or string, the schema source this page corresponds to (see
      MkDocsWeb.page_source_map)
    RETURN: string, `markdown_text` with a Mermaid "click" directive appended to every
    ```mermaid flowchart block (see diagram.render_tree) for each node whose label names a known
    Data Group/Enumeration, linking it to that Data Group/Enumeration's own section -- on this
    same page if it's defined in `source`, or a sibling specification page otherwise (every page
    rendered from add_schema_diagram/add_data_model lives at "specifications/<source>.md"; see
    MkDocsWeb.make_specification_pages).
    """

    def link_block(match):
        body = match.group(1)
        click_lines = []
        for node_match in _MERMAID_NODE_LINE.finditer(body):
            node_id, label = node_match.group(1), node_match.group(2)
            name = label[:-1] if label.endswith("*") else label
            anchor = reference_index.resolve(name, source)
            if anchor is None:
                continue
            defining_source = reference_index.source_of(name, source)
            url = f"#{anchor}" if defining_source == source else f"../{defining_source}/#{anchor}"
            click_lines.append(f'    click {node_id} "{url}" "{label}"')
        if not click_lines:
            return match.group(0)
        return "```mermaid\n" + body + "\n" + "\n".join(click_lines) + "\n```"

    return _MERMAID_BLOCK.sub(link_block, markdown_text)
