"""
Markdown grid-table creation utilities
"""

import copy
import io
import stringcase


def flatten(list_of_lists):
    """
    - list_of_lists: (list (list *)), a list of lists
    RETURN: (List *), the list flattened
    """
    return [item for sublist in list_of_lists for item in sublist]


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
    verbose = False
    if len(text) > 0:
        if text[0:1] in ["+ ", "- ", "* "]:
            text = "\\" + text
    if "\n" in text:
        return flatten([wrap_text_to_lines(t, width, bold, left_space, right_space) for t in text.split("\n")])
    atoms = text.split(" ")
    if bold:
        atoms[0] = "**" + atoms[0]
        atoms[-1] = atoms[-1] + "**"
    longest_atom = max([len(s) for s in atoms])
    if longest_atom + left_space + right_space > width:
        print("Warning! Need to hyphenate atoms!")
    lines = []
    atom_idx = 0
    first = True
    line = " " * left_space
    num_atoms = len(atoms)
    while atom_idx < num_atoms:
        if verbose:
            print(f"atom_idx: {atom_idx}")
            print(f"line    : {line}")
            print(f"lines   : {lines}")
            print(f"atoms   : {atoms}")
        if first:
            new_line = line + atoms[atom_idx]
            first = False
        else:
            new_line = line + " " + atoms[atom_idx]
        if len(new_line) + right_space <= width:
            line = new_line
        else:
            lines.append(line + " " * right_space)
            line = (" " * left_space) + atoms[atom_idx]
        atom_idx += 1
    if len(line) > 0:
        lines.append(line + " " * right_space)
    if verbose:
        print(f"line    : {line}")
        print(f"lines   : {lines}")
        print(f"atoms   : {atoms}")
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
        full_size = len(col_content)
        atoms = col_content.replace("\n", " ").split(" ")
        longest_atom = max([len(s) for s in atoms])
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
    table = write_row(columns, sizes, True)
    for row in rows:
        table += write_row(row, sizes, False)
    return table


def write_table(dat, columns, caption=None, preferred_sizes=None):
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
            handle.write(f"\nTable: {caption} {{#tbl:{stringcase.snakecase(caption)}}}\n")
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
