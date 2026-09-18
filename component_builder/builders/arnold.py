import logging
from typing import NamedTuple

import hou

from .. import base, model

logger = logging.getLogger(__name__)

ComponentType = model.Material.ComponentType


class ColorSpace(NamedTuple):
    color_family: str
    color_space: str


class ArnoldComponentBuilder(base.ComponentBuilder):
    def create_component(
        self, component: model.Component, parent: hou.LopNode
    ) -> tuple[hou.LopNode, ...]:
        all_nodes = super().create_component(component, parent)

        # Get ComponentGeometry node
        for node in all_nodes:
            if 'componentgeometry' in node.type().name():
                geometry_node = node
                break
        else:
            return all_nodes

        # Reposition
        for node in all_nodes:
            if node is geometry_node:
                continue
            node.move(hou.Vector2(0, -2))

        geometry_position = geometry_node.position()
        all_nodes = list(all_nodes)

        # Connections
        connections = {}
        for connection in geometry_node.outputConnections():
            connection_output_node = connection.outputNode()
            index = connection.inputIndex()
            if connection_output_node is not None:
                connections[connection_output_node] = index

        # Mesh Edit
        mesh_edit_node = parent.createNode('mesh')
        mesh_edit_node.setParms(
            {
                'primpattern': '%type:Mesh',
                'createprims': 0,
                'doubleSided_control': 'set',
                'doubleSided': True,
            }
        )
        mesh_edit_node.setPosition(geometry_position + hou.Vector2(0, -1))
        mesh_edit_node.setInput(0, geometry_node)
        output_node = mesh_edit_node
        all_nodes.append(mesh_edit_node)

        # Render Geometry Settings
        if (
            component.material
            and ComponentType.DISPLACEMENT in component.material.textures
        ):
            settings_node = create_render_geometry_settings(parent)
            settings_node.setPosition(geometry_position + hou.Vector2(0, -2))
            all_nodes.append(settings_node)
            output_node = settings_node

        # Reconnect
        for node, index in connections.items():
            node.setInput(index, output_node)

        return tuple(all_nodes)

    def create_material(
        self, material: model.Material, parent: hou.LopNode
    ) -> hou.VopNode:
        builder = parent.createNode(
            'arnold_materialbuilder', material.name, force_valid_node_name=True
        )
        assert isinstance(builder, hou.VopNode), 'invalid node: arnold_materialbuilder'

        out = builder.node('OUT_material')
        assert out is not None, 'invalid node: OUT_Material'

        # Standard Surface
        surface = builder.createNode('arnold::standard_surface')
        out.setInput(0, surface)

        # Values
        if material.thin_walled:
            surface.setParms({'thin_walled': True})
        values = {c.value: v for c, v in material.values.items()}
        surface.setParms(values)

        # Textures
        for component_type, texture in material.textures.items():
            if not texture.path:
                logger.warning(f'Empty texture path for component: {component_type}')
                continue

            name = f'image_{component_type}'

            if texture.color_space:
                color_space = self._get_color_space(texture.color_space)
            else:
                color_space = self._get_default_color_space(component_type)

            # Displacement
            if component_type == ComponentType.DISPLACEMENT:
                image_node = create_image(
                    parent=builder,
                    name=name,
                    filename=texture.path,
                    color_space=color_space,
                )
                if material.triplanar:
                    triplanar_node = create_triplanar(
                        parent=builder, scale=material.triplanar_scale
                    )
                    triplanar_node.setInput(0, image_node)
                    out.setInput(1, triplanar_node)
                else:
                    out.setInput(1, image_node)
                continue

            index = surface.inputIndex(component_type.value)
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
            output_node = image_node

            # Normal Map
            if component_type == ComponentType.NORMAL:
                normal_map_node = builder.createNode('arnold::normal_map')
                normal_map_node.setInput(0, image_node)
                output_node = normal_map_node

            # Triplanar
            if material.triplanar:
                triplanar_node = create_triplanar(
                    parent=builder, scale=material.triplanar_scale
                )
                triplanar_node.setInput(0, output_node)
                output_node = triplanar_node

            surface.setInput(index, output_node)

        builder.layoutChildren()

        return builder

    @staticmethod
    def _get_default_color_space(
        component_type: ComponentType,
    ) -> ColorSpace:
        """Return the color family and color space for a ComponentType."""

        # NOTE: Currently assumes ACES v1.2 ocio config.

        color_family = 'Utility'

        default_colorspace = {
            ComponentType.BASE_COLOR: 'sRGB - Texture',
            ComponentType.SPECULAR_COLOR: 'sRGB - Texture',
            ComponentType.TRANSMISSION_COLOR: 'sRGB - Texture',
            ComponentType.SUBSURFACE_COLOR: 'sRGB - Texture',
            ComponentType.EMISSION_COLOR: 'sRGB - Texture',
        }

        color_space = default_colorspace.get(component_type, 'Raw')
        return ColorSpace(color_family, color_space)

    @staticmethod
    def _get_color_space(name: str) -> ColorSpace:
        """
        Return the color family and color space from a name from the ACES OCIO config.
        """

        color_spaces: dict[str, ColorSpace] = {
            'srgb_texture': ColorSpace('Utility', 'sRGB - Texture'),
            'lin_rec709': ColorSpace('Utility', 'Linear Rec.709 (sRGB)'),
            'g22_rec709': ColorSpace('Utility', 'Gamma 2.2 Rec.709 - Texture'),
            'g18_rec709': ColorSpace('Utility', 'Gamma 1.8 Rec.709 - Texture'),
            'acescg': ColorSpace('ACES', 'ACEScg'),
            'lin_ap1': ColorSpace('ACES', 'ACEScg'),
            'lin_srgb': ColorSpace('Utility', 'Linear Rec.709 (sRGB)'),
        }

        # Unsupported names
        # g22_ap1
        # g18_ap1
        # adobergb
        # lin_adobergb
        # srgb_displayp3
        # lin_displayp3

        color_space = color_spaces.get(name, ColorSpace('Utility', 'Raw'))
        return color_space


def create_image(
    parent: hou.VopNode,
    name: str | None = None,
    filename: str = '',
    color_space: ColorSpace | None = None,
    ignore_missing_textures: bool = True,
) -> hou.VopNode:
    """Create and return an image node."""

    if color_space is None:
        color_space = ColorSpace('Utility', 'Raw')

    filename = filename.replace('\\', '/')
    node = parent.createNode('arnold::image', name, force_valid_node_name=True)
    node.setParms(
        {
            'filename': filename,
            'color_family': color_space.color_family,
            'color_space': color_space.color_space,
            'ignore_missing_textures': ignore_missing_textures,
        }
    )

    return node


def create_triplanar(
    parent: hou.VopNode, name: str | None = None, scale: hou.Vector3 | None = None
) -> hou.VopNode:
    """Create and return a Triplanar node."""

    node = parent.createNode('arnold::triplanar', name, force_valid_node_name=True)
    if scale is not None:
        node.setParms({'scale': scale})

    return node


def create_render_geometry_settings(
    parent: hou.LopNode, name: str | None = None
) -> hou.LopNode:
    """Create and return a RenderGeometrySettings node."""

    node = parent.createNode('rendergeometrysettings', name, force_valid_node_name=True)
    # NOTE: Set most parameters to default values to make it easier for the user to
    # start setting custom values.
    values = {
        'primpattern': f'{base.ROOT_PRIM}/geo/*',
        hou.text.encode('primvars:arnold:subdiv_type_control'): 'set',
        hou.text.encode('primvars:arnold:subdiv_iterations_control'): 'set',
        hou.text.encode('primvars:arnold:subdiv_adaptive_error_control'): 'set',
        hou.text.encode('primvars:arnold:subdiv_adaptive_error'): 0.1,
        hou.text.encode('primvars:arnold:subdiv_adaptive_space_control'): 'set',
        hou.text.encode('primvars:arnold:subdiv_adaptive_space'): 'object',
        hou.text.encode('primvars:arnold:disp_height_control'): 'set',
        hou.text.encode('primvars:arnold:disp_zero_value_control'): 'set',
        hou.text.encode('primvars:arnold:disp_zero_value'): 0.5,
        hou.text.encode('primvars:arnold:disp_padding_control'): 'set',
    }
    node.setParms(values)

    return node
