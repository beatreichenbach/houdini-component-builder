from __future__ import annotations

from collections.abc import Sequence

import hou


def get_current_node() -> hou.Node | None:
    """Return the Node of the active NetworkEditor."""

    if not hou.isUIAvailable():
        return None

    current_pane = hou.ui.paneTabOfType(hou.paneTabType.NetworkEditor)
    if isinstance(current_pane, hou.NetworkEditor):
        return current_pane.pwd()
    return None


def get_bounding_box(nodes: Sequence[hou.NetworkMovableItem]) -> hou.BoundingRect:
    """Return the BoundingRect for Nodes."""

    bbox = hou.BoundingRect()
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
