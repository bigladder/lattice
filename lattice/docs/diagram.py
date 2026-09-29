"""
Mermaid diagram generation for a schema's Data Group hierarchy: which Data Groups a given
Data Group references (directly or through an array) via another Data Element, walked from a
root Data Group.
"""

import re

from ..schema import DataGroupType

_GROUP_REFERENCE_PATTERN = DataGroupType.pattern.pattern


def _slugify(path):
    """
    - path: array of string, the node names from the diagram root down to and including a node
    RETURN: string, a Mermaid-safe node id unique to that path
    """
    return "n_" + "_".join(re.sub(r"[^A-Za-z0-9]+", "_", part).strip("_") for part in path)


def _emit_node(node, parent_id, path, lines):
    """
    - node: dict, a {"name": string, "subcategories": [...]} tree node (subcategories optional),
      or a {"name": string, "recursive_target_path": array of string} back-reference to an
      already-emitted ancestor node (see build_data_group_tree)
    - parent_id: None or string, the Mermaid node id of this node's parent
    - path: array of string, the ancestor node names above this node (not including it)
    - lines: array of string, Mermaid flowchart body lines, appended to in place
    RETURN: None
    """
    target_path = node.get("recursive_target_path")
    if target_path is not None:
        # A repeated (e.g. self-referencing) Data Group: draw a cycle back to the node already
        # emitted for it, rather than a new box, so the diagram shows an actual loop instead of a
        # dead-end that reads as a distinct, one-off child.
        if parent_id is not None:
            lines.append(f"    {parent_id} --> {_slugify(target_path)}")
        return
    name = node["name"]
    node_path = path + [name]
    node_id = _slugify(node_path)
    label = name.replace('"', "'")
    if parent_id is None:
        lines.append(f'    {node_id}["{label}"]')
    else:
        lines.append(f'    {parent_id} --> {node_id}["{label}"]')
    for child in node.get("subcategories", []):
        _emit_node(child, node_id, node_path, lines)


def render_tree(roots, caption=None):
    """
    - roots: array of dict, each a recursive {"name": string, "subcategories": [...]} structure
    - caption: None or string, an optional caption placed above the diagram
    RETURN: string, a fenced ```mermaid flowchart in Markdown
    """
    lines = ["%%{init: {'flowchart': {'curve': 'basis'}}}%%", "flowchart TD"]
    for root in roots:
        _emit_node(root, None, [], lines)
    diagram = "```mermaid\n" + "\n".join(lines) + "\n```\n"
    if caption:
        diagram = f"**{caption}**\n\n" + diagram
    return diagram


def _referenced_group_name(type_string):
    """
    - type_string: string, a Data Element's `Type` value, e.g. "Array(Group(EndUse))",
      "Group(TimeSeries)", "{EndUse}", or a non-group type such as "String" or "<SomeEnum>"
    RETURN: None or string, the referenced Data Group's name, if `type_string` references one
      (through either the spelled-out `Group(X)` form or the compact `{X}` form, at any depth,
      e.g. wrapped in Array(...))
    """
    match = _GROUP_REFERENCE_PATTERN.search(type_string)
    return match.group("DataGroupName") if match is not None else None


def _referenced_groups(data, group_name):
    """
    - data: dict, a loaded *.schema.yaml file's contents
    - group_name: string, a Data Group's name
    RETURN: array of (string, bool) tuples, the name of each Data Group referenced by one of
      `group_name`'s Data Elements (through a `Group(X)` or `Array(Group(X))` type, in either
      spelled-out or compact form), paired with whether that Data Element is required. A Data
      Group defined outside this schema file (e.g. a Standard 232 common data group) yields no
      children of its own further down, since it isn't present in `data` to recurse into.
    """
    group = data.get(group_name)
    if not isinstance(group, dict):
        return []
    referenced = []
    for element in group.get("Data Elements", {}).values():
        target = _referenced_group_name(element.get("Type", ""))
        if target is not None:
            referenced.append((target, bool(element.get("Required", False))))
    return referenced


def build_data_group_tree(data, group_name, required=True, ancestors=()):
    """
    - data: dict, a loaded *.schema.yaml file's contents
    - group_name: string, the Data Group to build a tree node for
    - required: bool, whether the Data Element that references `group_name` is required --
      carried into the rendered label as the same "*" (not required) marker used in hand-written
      Data Group Hierarchy sections
    - ancestors: tuple of (string, array of string) pairs, each an ancestor Data Group's name
      paired with its own rendered node path (in render_tree's path terms), used both to stop
      recursion at a repeated (e.g. self-referencing) Data Group and to point a cycle back at the
      exact node already emitted for it
    RETURN: dict, a {"name": string, "subcategories": [...]} node suitable for render_tree, or a
      {"name": string, "recursive_target_path": array of string} back-reference node
    """
    label = group_name if required else f"{group_name}*"
    parent_path = ancestors[-1][1] if ancestors else []
    my_path = parent_path + [label]
    for ancestor_name, ancestor_path in ancestors:
        if ancestor_name == group_name:
            return {"name": label, "recursive_target_path": ancestor_path}
    children = [
        build_data_group_tree(
            data, child_name, required=child_required, ancestors=(*ancestors, (group_name, my_path))
        )
        for child_name, child_required in _referenced_groups(data, group_name)
    ]
    node = {"name": label}
    if children:
        node["subcategories"] = children
    return node
