"""
Mermaid diagram generation for a schema's Data Group hierarchy: which Data Groups a given
Data Group references (directly or through an array) via another Data Element, walked from a
root Data Group.
"""

from __future__ import annotations

import re
from typing import Any

from ..schema import DataGroup


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


def build_data_group_tree(
    data_group: DataGroup,
    required: bool = True,
    ancestors: tuple[tuple[DataGroup, list[str]], ...] = (),
) -> dict[str, Any]:
    """
    - data_group: lattice.schema.DataGroup, the Data Group to build a tree node for -- already
      resolved (see DataGroup.referenced_children), so a common Data Group defined outside this
      schema file (e.g. a Standard 232 common data group from `core` or a declared Reference) is
      walked into just like a locally-defined one, instead of stopping as a leaf
    - required: bool, whether the Data Element that references `data_group` is required --
      carried into the rendered label as the same "*" (not required) marker used in hand-written
      Data Group Hierarchy sections
    - ancestors: tuple of (DataGroup, array of string) pairs, each an ancestor Data Group paired
      with its own rendered node path (in render_tree's path terms), used both to stop recursion
      at a repeated (e.g. self-referencing) Data Group and to point a cycle back at the exact
      node already emitted for it. Ancestors are compared by identity, not name, since two
      different schemas may each define a same-named Data Group (e.g. "Description").
    RETURN: dict, a {"name": string, "subcategories": [...]} node suitable for render_tree, or a
      {"name": string, "recursive_target_path": array of string} back-reference node
    """
    label = data_group.name if required else f"{data_group.name}*"
    parent_path = ancestors[-1][1] if ancestors else []
    my_path = parent_path + [label]
    for ancestor_group, ancestor_path in ancestors:
        if ancestor_group is data_group:
            return {"name": label, "recursive_target_path": ancestor_path}
    children = [
        build_data_group_tree(child, required=bool(element.required), ancestors=(*ancestors, (data_group, my_path)))
        for element, child in data_group.referenced_children()
        if isinstance(child, DataGroup)
    ]
    node: dict[str, Any] = {"name": label}
    if children:
        node["subcategories"] = children
    return node
