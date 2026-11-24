import logging
from typing import cast

import hou

from .. import base, model
from ..color_space import (
    ColorSpace,
    get_color_space,
    get_default_color_space_name,
)
from ..exceptions import ComponentBuilderError
from ..utils import create_node

logger = logging.getLogger(__name__)


class ArnoldComponentBuilder(base.ComponentBuilder):
    def post_geometry(
        self,
        geometry: model.Geometry,
        parent: hou.LopNode | hou.LopNetwork,
        geometry_node: hou.LopNode,
    ) -> tuple[hou.LopNode, ...]:
        created_nodes: list[hou.LopNode] = []

        anchor_position = geometry_node.position()

        # Mesh Edit
        mesh_edit_node = parent.createNode('mesh')
        mesh_edit_node = cast(hou.LopNode, mesh_edit_node)
        mesh_edit_node.setParms(
            {
                'primpattern': '%type:Mesh',
                'createprims': 0,
                'doubleSided_control': 'set',
                'doubleSided': True,
            }
        )
        mesh_edit_node.setPosition(anchor_position + hou.Vector2(0, -1))
        mesh_edit_node.setInput(0, geometry_node)
        created_nodes.append(mesh_edit_node)

        # Render Geometry Settings
        settings_node = create_render_geometry_settings(parent)
        settings_node.setPosition(anchor_position + hou.Vector2(0, -2))
        settings_node.setInput(0, mesh_edit_node)
        created_nodes.append(settings_node)

        return tuple(created_nodes)

    def create_material(
        self, material: model.Material, parent: hou.LopNode
    ) -> hou.VopNode:
        builder = create_node(
            'arnold_materialbuilder', parent, hou.VopNode, material.name
        )

        out_name = 'OUT_material'
        out = builder.node(out_name)
        if out is None:
            raise ComponentBuilderError(f'missing child node: {out_name!r}')

        # Standard Surface
        surface = builder.createNode('arnold::standard_surface')
        out.setInput(0, surface)

        # Values
        if material.thin_walled:
            surface.setParms({'thin_walled': True})
        values = {get_arnold_component(c): v for c, v in material.values.items()}
        surface.setParms(values)

        # Textures
        for component_type, texture in material.textures.items():
            if not texture.path:
                logger.warning(f'Empty texture path for component: {component_type}')
                continue

            name = f'image_{component_type}'

            color_space_name = texture.color_space
            if not color_space_name and material.use_default_color_space:
                color_space_name = get_default_color_space_name(component_type)

            color_space = get_color_space(color_space_name)
            if color_space_name and color_space is None:
                logger.warning(f'Unknown OCIO color space {color_space_name!r}.')

            # Displacement
            if component_type == model.ComponentType.DISPLACEMENT:
                image_node = create_image(
                    parent=builder,
                    name=name,
                    filename=texture.path,
                    color_space=color_space,
                )
                tail = image_node
                if material.triplanar:
                    triplanar_node = create_triplanar(
                        parent=builder, scale=material.triplanar_scale
                    )
                    triplanar_node.setInput(0, image_node)
                    tail = triplanar_node
                out.setInput(1, tail)
                continue

            component_name = get_arnold_component(component_type)
            index = surface.inputIndex(component_name)
            if index < 0:
                logger.warning(f'Invalid channel for StandardSurface: {component_type}')
                continue

            # Channels
            image_node = create_image(
                parent=builder,
                name=name,
                filename=texture.path,
                color_space=color_space,
            )
            tail = image_node

            # Triplanar
            if material.triplanar:
                triplanar_node = create_triplanar(
                    parent=builder, scale=material.triplanar_scale
                )
                triplanar_node.setInput(0, tail)
                tail = triplanar_node

            # Normal Map
            if component_type == model.ComponentType.NORMAL:
                normal_map_node = builder.createNode('arnold::normal_map')
                normal_map_node.setInput(0, tail)
                tail = normal_map_node

            surface.setInput(index, tail)

        builder.layoutChildren()

        return builder

def create_image(
    parent: hou.VopNode,
    name: str | None = None,
    filename: str = '',
    color_space: ColorSpace | None = None,
    ignore_missing_textures: bool = True,
) -> hou.VopNode:
    """Create and return an image node."""

    filename = filename.replace('\\', '/')
    node = create_node('arnold::image', parent, hou.VopNode, name)
    parms: dict[str, str | bool] = {
        'filename': filename,
        'ignore_missing_textures': ignore_missing_textures,
    }
    if color_space is not None:
        parms['color_family'] = color_space.color_family
        parms['color_space'] = color_space.color_space

    node.setParms(parms)

    return node


def create_triplanar(
    parent: hou.VopNode, name: str | None = None, scale: float = 1
) -> hou.VopNode:
    """Create and return a Triplanar node."""

    node = create_node('arnold::triplanar', parent, hou.VopNode, name)
    node.setParms({'scale': (scale, scale, scale)})

    return node


def create_render_geometry_settings(
    parent: hou.LopNode | hou.LopNetwork, name: str | None = None
) -> hou.LopNode:
    """Create and return a RenderGeometrySettings node."""

    node = create_node('rendergeometrysettings', parent, hou.LopNode, name)

    # NOTE: Set most parameters to default values to make it easier for the user to
    # start setting custom values.
    values = {
        'primpattern': f'{base.ROOT_PRIM}/geo/*',
        hou.text.encode('primvars:arnold:subdiv_type_control'): 'set',
        hou.text.encode('primvars:arnold:subdiv_type'): 'catclark',
        hou.text.encode('primvars:arnold:subdiv_iterations_control'): 'set',
        hou.text.encode('primvars:arnold:subdiv_iterations'): 4,
        hou.text.encode('primvars:arnold:subdiv_adaptive_error_control'): 'set',
        hou.text.encode('primvars:arnold:subdiv_adaptive_error'): 0.1,
        hou.text.encode('primvars:arnold:subdiv_adaptive_space_control'): 'set',
        hou.text.encode('primvars:arnold:subdiv_adaptive_space'): 'object',
        hou.text.encode('primvars:arnold:disp_height_control'): 'set',
        hou.text.encode('primvars:arnold:disp_height'): 0.01,
        hou.text.encode('primvars:arnold:disp_zero_value_control'): 'set',
        hou.text.encode('primvars:arnold:disp_zero_value'): 0.5,
        hou.text.encode('primvars:arnold:disp_padding_control'): 'set',
        hou.text.encode('primvars:arnold:disp_padding'): 0.1,
    }
    node.setParms(values)

    return node


def get_arnold_component(component_type: model.ComponentType) -> str:
    """Return the Arnold component name from a ComponentType."""

    names = {c: c.value for c in model.ComponentType}
    names[model.ComponentType.SPECULAR_IOR] = 'specular_IOR'
    name = names[component_type]
    return name
