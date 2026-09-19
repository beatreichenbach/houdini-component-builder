import os
from collections.abc import Sequence
from typing import TypeVar

import hou

T = TypeVar('T', bound=hou.OpNode)


def create_node(
    node_type: str, parent: hou.OpNode, cls: type[T], name: str | None = None
) -> T:
    """Return a newly created node."""

    node = parent.createNode(node_type, name, force_valid_node_name=True)
    if not isinstance(node, cls):
        raise ValueError(f'expected type {cls.__name__!r}, got {type(node).__name__!r}')

    return node


def get_node(path: str, parent: hou.OpNode, cls: type[T]) -> T:
    """Return the child node."""

    node = parent.node(path)
    if node is None:
        raise ValueError(f'missing child node: {path!r}')
    if not isinstance(node, cls):
        raise ValueError(f'expected type {cls.__name__!r}, got {type(node).__name__!r}')
    return node


def get_current_node() -> hou.OpNode | None:
    """Return the Node of the active NetworkEditor."""

    if not hou.isUIAvailable():
        return None

    current_pane = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    if isinstance(current_pane, hou.NetworkEditor):
        node = current_pane.pwd()
        if isinstance(node, hou.OpNode):
            return node
    return None


def get_bounding_box(nodes: Sequence[hou.NetworkMovableItem]) -> hou.BoundingRect:
    """Return the BoundingRect for Nodes."""

    bbox = hou.BoundingRect()  # type: ignore[ty:missing-argument]
    for node in nodes:
        bbox.enlargeToContain(node.position())
        bbox.enlargeToContain(node.position() + node.size())
    return bbox


def layout_nodes(nodes: Sequence[hou.Node], margin: hou.Vector2 | None = None) -> None:
    """Lay out the nodes in an empty area of the NetworkEditor."""

    if not nodes:
        return

    if margin is None:
        margin = hou.Vector2(1, 0)

    parent = nodes[0].parent()
    if parent is None:
        return

    all_items = parent.allItems()
    existing_items = [item for item in all_items if item not in nodes]
    existing_bbox = get_bounding_box(existing_items)

    loaded_bbox = get_bounding_box(nodes)

    if existing_bbox.isValid():
        target_position = existing_bbox.max() + margin
        source_position = hou.Vector2(loaded_bbox.min().x(), loaded_bbox.max().y())
        offset = target_position - source_position
        for node in nodes:
            node.move(offset)


def sanitize_path(path: str) -> str:
    """Return a sanitized path for Houdini nodes."""

    sanitized = path.replace('\\', '/')
    file_path = hou.hipFile.path()
    if file_path:
        project_dir = os.path.dirname(file_path).replace('\\', '/')
        sanitized = sanitized.replace(project_dir, '$HIP')

    return sanitized
