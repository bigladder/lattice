"""
Markdown grid-table creation utilities
"""

import copy
import io
import re

import casefy


def flatten(list_of_lists):
    """
    - list_of_lists: (list (list *)), a list of lists
    RETURN: (List *), the list flattened
    """
    return [item for sublist in list_of_lists for item in sublist]


def scoped_anchor_id(name, scope=None):
    """
    - name: string, the name to build an id from (e.g. a Data Group or Enumeration name, or a
      table caption)
    - scope: None or string, a namespace to prefix the id with (e.g. the schema source it came
      from), so the same name defined in two different schema files doesn't collide
    RETURN: string, a stable, snake_cased anchor id
    """
    slug = casefy.snakecase(name)
    return f"{casefy.snakecase(scope)}:{slug}" if scope is not None else slug


# Markdown syntax that a renderer consumes as punctuation rather than showing as characters:
# inline code spans, links (inline and reference-style, keeping only the visible link text and
# dropping the target/reference id entirely), emphasis/strong, superscript/subscript (this
# schema format uses `^2^` for unit exponents, e.g. "m^2^"), and trailing attr_list annotations
# (e.g. "{: .md-button }"). Applied repeatedly (innermost-first) so nested markup -- e.g. a link
# whose visible text is itself a code span -- resolves the same way regardless of which layer
# is written first.
_ATTR_LIST = re.compile(r"\{:[^}]*\}")
_LINK = re.compile(r"\[([^\]]*)\](?:\([^)]*\)|\[[^\]]*\])")
_CODE_SPAN = re.compile(r"`([^`]*)`")
_SUPER_OR_SUBSCRIPT = re.compile(r"(\^|~)([^\^~]+?)\1")
_EMPHASIS = re.compile(r"(\*\*\*|\*\*|\*|___|__|_)([^*_]+?)\1")


def _strip_markdown_syntax(text):
    """
    - text: string, possibly containing Markdown syntax
    RETURN: string, `text` with any syntax markup removed, leaving only what a Markdown
    renderer would actually display. Used only to *measure* rendered width -- the literal
    markup itself is never altered in the text that actually gets written out.
    """
    previous = None
    while previous != text:
        previous = text
        text = _ATTR_LIST.sub("", text)
        text = _LINK.sub(r"\1", text)
        text = _CODE_SPAN.sub(r"\1", text)
        text = _SUPER_OR_SUBSCRIPT.sub(r"\2", text)
        text = _EMPHASIS.sub(r"\2", text)
    return text


def visual_length(text):
    """
    - text: string, possibly containing Markdown syntax
    RETURN: int, how many characters of `text` would actually be visible once rendered as
    Markdown. Used in place of `len()` when deciding column proportions and word-wrap points, so
    that syntax overhead (backticks, link brackets, emphasis markers, ...) doesn't inflate a
    cell's apparent size. It is never used to decide the final real column width written to
    disk -- that must still fit every cell's literal (unstripped) character count, since the
    grid table's `+`/`|` borders have to line up at the same real character position on every
    row for `markdown-grid-tables` (or Pandoc) to parse the table at all.
    """
    return len(_strip_markdown_syntax(text))


# A line's leading structure, which a wrapped continuation line must hang under to stay inside
# it: indentation, a definition's ":   ", and a list item's marker.
_LINE_PREFIX = re.compile(r"^ *(?::\s+)?(?:(?:[-*+]|\d+[.)])\s+)?")

# A word that starts a block -- a list item, heading, quote, definition, reference definition,
# setext underline, or rule -- whenever it begins a line.
_BLOCK_MARKER = re.compile(r"^(?:[-*+>:|]|#{1,6}|\d+[.)]|=+|-{3,}|\*{3,}|_{3,}|\[[^\]]*\]:)$")


def _split_atoms(text):
    """
    - text: string, one line of cell text (no newlines), without its leading structure
    RETURN: (Array string), the pieces a wrap may break between

    Splits on spaces, except inside a code span, a link (`[...]`), or an attr_list (`{...}`),
    whose inner spaces a line break would change the meaning of. A block marker is glued to the
    piece before it, so that no wrap can start a continuation line with it.
    """
    atoms = []
    current = ""
    in_code = False
    bracket_depth = 0
    brace_depth = 0
    for char in text:
        if char == "`":
            in_code = not in_code
        elif not in_code:
            if char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth = max(0, bracket_depth - 1)
            elif char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth = max(0, brace_depth - 1)
        if char == " " and not in_code and bracket_depth == 0 and brace_depth == 0:
            atoms.append(current)
            current = ""
        else:
            current += char
    atoms.append(current)
    glued: list[str] = []
    for atom in atoms:
        if glued and _BLOCK_MARKER.match(atom):
            glued[-1] += " " + atom
        else:
            glued.append(atom)
    return glued


def _line_atoms(line):
    """
    - line: string, one line of cell text (no newlines)
    RETURN: (int, Array string), the hanging indent for its continuation lines, and its
    unbreakable pieces -- the first carrying the line's leading structure (see _LINE_PREFIX)
    """
    match = _LINE_PREFIX.match(line)
    prefix = match.group(0) if match else ""
    atoms = _split_atoms(line[len(prefix) :])
    atoms[0] = prefix + atoms[0]
    return len(prefix), atoms


# pylint: disable-next=too-many-branches
def wrap_text_to_lines(text, width, bold=False, left_space=1, right_space=1):
    """
    - text: string, the text to wrap
    - width: int, >0, the width to wrap to
    - bold: bool, if True, allow space for surrounding the beginning and end with **
    - left_space: int, >=0, the left space to enforce between cells
    - right_space: int, >=0, the right space to enforce between cells
    NOTE: width includes both left_space and right_space
    RETURN: (Array String), the lines
    """
    if len(text) > 0:
        if text[0:1] in ["+ ", "- ", "* "]:
            text = "\\" + text
    if "\n" in text:
        return flatten([wrap_text_to_lines(t, width, bold, left_space, right_space) for t in text.split("\n")])
    # Breaks only between unbreakable pieces, and measures in literal characters: every row of a
    # grid table has to put its borders at the same real position, Markdown syntax included.
    hang, atoms = _line_atoms(text)
    if bold:
        atoms[0] = "**" + atoms[0]
        atoms[-1] = atoms[-1] + "**"
    lines: list[str] = []
    line = " " * left_space + atoms[0]
    for atom in atoms[1:]:
        candidate = line + " " + atom
        if len(candidate) + right_space <= width:
            line = candidate
        else:
            lines.append(line + " " * right_space)
            line = " " * (left_space + hang) + atom
    lines.append(line + " " * right_space)
    return lines


def get_line_row(lines, row):
    """
    - lines: (Array string), array of lines
    - row: int, >=0, the row index to grab
    RETURN: string, if row greater than or equal to lines length, returns ''
    """
    if row < len(lines):
        return lines[row]
    return ""


def write_rule(sizes, is_header=False):
    """
    - sizes: (Array int), the column widths (of contents)
    RETURN: string
    """
    mark = "=" if is_header else "-"
    return "+" + "".join([(mark * n + "+") for n in sizes]) + "\n"


def write_row(content, sizes, is_header=False):
    """
    RETURN: string
    """
    assert len(content) == len(sizes), "len(content) must equal len(sizes)"
    table = write_rule(sizes) if is_header else ""
    list_of_lines = [wrap_text_to_lines(text=content[n], width=sizes[n], bold=is_header) for n in range(len(content))]
    for row_num in range(max([len(lines) for lines in list_of_lines])):
        table_line = "|" + "".join(["{:" + str(n) + "s}|" for n in sizes]) + "\n"
        texts = [get_line_row(lines, row_num) for lines in list_of_lines]
        table += table_line.format(*texts)
    table += write_rule(sizes, is_header=is_header)
    return table


# pylint: disable-next=too-many-branches, too-many-locals
def get_column_sizes(content, is_bold=False, has_spacing=True, preferred_sizes=None, full_width=100):
    """
    - content: (Array string), the column content
    - is_bold: Bool, True if the column content must be surrounded with '**'
    - has_spacing: Bool, True if we keep at least one space padding between cell border
    - preferred_sizes: None or (Array int), the preferred sizes of the columns.
      Will be at least this size
    - full_width: Should be same as --columns Pandoc argument
      Pandoc default=72
    RETURN: (Array int), the actual sizes
    """
    if preferred_sizes is None:
        sizes = [0] * len(content)
    else:
        sizes = copy.deepcopy(preferred_sizes)
    full_sizes = copy.deepcopy(sizes)
    size_diff = [0] * len(sizes)
    max_diff_col = 0
    assert len(content) == len(sizes), "len(content) must equal len(sizes)"
    for col_num, col_content in enumerate(content):
        full_size = visual_length(col_content)
        atoms = col_content.replace("\n", " ").split(" ")
        longest_atom = max([visual_length(s) for s in atoms])
        if is_bold:
            num_atoms = len(atoms)
            if num_atoms == 1:
                longest_atom += 4
            elif num_atoms > 1:
                longest_atom += 2
            full_size += 4
        if has_spacing:
            longest_atom += 2
            full_size += 2
        if longest_atom > sizes[col_num]:
            sizes[col_num] = longest_atom
        if full_size > full_sizes[col_num]:
            full_sizes[col_num] = full_size
        size_diff[col_num] = full_sizes[col_num] - sizes[col_num]
        if size_diff[col_num] > size_diff[max_diff_col]:
            max_diff_col = col_num
    if sum(full_sizes) < full_width:
        # full text will fit on one line, no need to make anything smaller
        return full_sizes
    if sum(sizes) >= full_width:
        # Sizes are too big already...things will be too tight to make any changes
        return sizes

    # Relax some sizes to fill in full width
    # Weigh towards columns with more text
    remaining_space = full_width - sum(sizes)
    total_diff = sum(size_diff)
    for col_num, _ in enumerate(sizes):
        sizes[col_num] += size_diff[col_num] * remaining_space // total_diff
    # Check remaining size
    remaining_space = full_width - sum(sizes)
    if remaining_space > 0:
        # Add remaining space to column with largest size diff
        sizes[max_diff_col] += remaining_space

    return sizes


def check_dict_of_arrays(doa, columns):
    """
    Checks the data-structure that dict of arrays has at least the keys in
    columns and that each entry's length is the same as the others.
    - doa: (Dict String (Array String)), dictionary with string keys to arrays of string
    - columns: (Array String), the columns of doa
    RETURN: (Array String), array of issues
    """
    issues = []
    length = None
    for col in columns:
        if col not in doa:
            issues.append(f"{col} not in doa")
            continue
        if length is None:
            try:
                length = len(doa[col])
            except TypeError:
                issues.append(f"could not take length of doa['{col}']")
        elif len(doa[col]) != length:
            issues.append(f"len(doa['{col}']) = {len(doa[col])} != {length}," + " the length of other columns")
    return issues


def assert_doa_valid(doa, columns):
    """
    Checks if DOA valid. If not, raises an exception.
    - doa: (Dict String (Array String)), dictionary with string keys to arrays of string
    - columns: (Array String), order of keys to write table out as
    """
    issues = check_dict_of_arrays(doa, columns)
    if len(issues) > 0:
        raise Exception("DictOfArraysInvalid: " + ";".join(issues))


def remove_blank_columns(doa, columns, sizes):
    """
    Remove columns that are blank.
    - doa: (Dict String (Array String)), dictionary with string keys to arrays of string
    - columns: (Array String), order of keys to write table out as
    RETURN: (Tuple (Array String), (Array Integer)), tuple of new columns with
    blanks removed and new sizes
    """
    new_columns = []
    new_sizes = []
    for col, size in zip(columns, sizes):
        non_blanks = 0
        for row in doa[col]:
            if row is not None and row != "":
                non_blanks += 1
        if non_blanks > 0:
            new_columns.append(col)
            new_sizes.append(size)
    return new_columns, new_sizes


def _real_width_floor(doa, columns):
    """
    - doa: (Dict String (Array String)), dictionary with string keys to arrays of string
    - columns: (Array String), the columns to compute a floor for
    RETURN: (Array int), for each column, the narrowest literal (unstripped) width that still
    fits every row `wrap_text_to_lines` could write for that column's header or cells.

    `get_column_sizes` measures against `visual_length`, so it may choose a column narrower than
    a cell's literal text whenever that cell carries Markdown syntax overhead (backticks, links,
    ...). But the grid table's `+`/`|` borders must land at the same real character position on
    every row or `markdown-grid-tables` (or Pandoc) can't parse it, so the column has to fit what
    `wrap_text_to_lines` actually writes. It breaks only between unbreakable pieces (see
    _line_atoms), so the widest row it can be forced into is one piece on its own: the first
    piece of a line, or any later one after its continuation line's hanging indent. That width,
    padded the same way `get_column_sizes` pads -- bold **markers** on the header, the +2
    spacing `has_spacing` always adds here -- is the floor.
    """
    floor = []
    for column in columns:
        cells = [(column, True)] + [(cell, False) for cell in doa[column]]
        column_floor = 0
        for cell, is_bold in cells:
            for line in cell.split("\n"):
                hang, atoms = _line_atoms(line)
                widest = max([len(atoms[0])] + [hang + len(atom) for atom in atoms[1:]])
                full_size = widest + 2  # +2: has_spacing is always True in make_table_from_dict_of_arrays
                if is_bold:
                    full_size += 4 if len(atoms) == 1 else 2
                column_floor = max(column_floor, full_size)
        floor.append(column_floor)
    return floor


def make_table_from_dict_of_arrays(doa, columns, preferred_sizes=None, drop_blank_columns=False):
    """
    - doa: (Dict String (Array String)), dictionary with string keys to arrays of string
    - columns: (Array String), order of keys to write table out as
    - preferred_sizes: None or (Array Int) with preferred column sizes
    - drop_blank_columns: Bool, if True, drops columns where there are no
      entries for any rows in that columns
    RETURN: String, a grid table
    """
    if preferred_sizes is None:
        preferred_sizes = [0] * len(columns)
    if drop_blank_columns:
        columns, preferred_sizes = remove_blank_columns(doa, columns, preferred_sizes)
    assert_doa_valid(doa, columns)
    full_width = 100
    sizes = get_column_sizes(
        columns, is_bold=True, has_spacing=True, preferred_sizes=preferred_sizes, full_width=full_width
    )
    num_rows = len(doa[columns[0]])
    rows = []
    for row_num in range(num_rows):
        row = [doa[c][row_num] for c in columns]
        rows.append(row)
        sizes = get_column_sizes(row, is_bold=False, has_spacing=True, preferred_sizes=sizes, full_width=full_width)
    sizes = [max(size, floor) for size, floor in zip(sizes, _real_width_floor(doa, columns))]
    table = write_row(columns, sizes, True)
    for row in rows:
        table += write_row(row, sizes, False)
    return table


def write_table(dat, columns, caption=None, preferred_sizes=None, scope=None):
    """
    - dat: (Dict String (Array String)), dict of arrays of data for the table
    - columns: (Array String), the column names in desired order
    - path: string, path to where to save the table
    - caption: None or string
    - preferred_sizes: None or (Array Integer), the preferred column sizes;
      column will be at least that size
    RETURN: string of the table in Markdown
    """
    if preferred_sizes is None:
        preferred_sizes = [0] * len(columns)
    the_str = ""
    with io.StringIO() as handle:
        handle.write(make_table_from_dict_of_arrays(dat, columns=columns, preferred_sizes=preferred_sizes))
        if caption is not None:
            handle.write(f"\nTable: {caption} {{#tbl:{scoped_anchor_id(caption, scope)}}}\n")
        the_str = handle.getvalue()
    return the_str


def write_out_table(dat, columns, path, caption, preferred_sizes=None):
    """
    - dat: (Dict String (Array String)), dict of arrays of data for the table
    - columns: (Array String), the column names in desired order
    - path: string, path to where to save the table
    - caption: None or string
    - preferred_sizes: None or (Array Integer), the preferred column sizes;
      column will be at least that size
    - table_size: None or string, if string, one of "Huge", "huge", "LARGE",
      "Large", "large", "normalsize", "small", "footnotesize", "scriptsize",
      "tiny" the table size
    RETURN: None
    SIDE_EFFECT: create table and write it to path as a pandoc grid table
    """
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(write_table(dat, columns, caption, preferred_sizes))
