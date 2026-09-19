import logging
from typing import NamedTuple, cast

import hou

from .. import base, model
from ..exceptions import ComponentBuilderError
from ..utils import create_node

logger = logging.getLogger(__name__)


class ColorSpace(NamedTuple):
    color_family: str
    color_space: str


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

            if texture.color_space:
                color_space = self._get_color_space(texture.color_space)
            else:
                color_space = self._get_default_color_space(component_type)

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

    @staticmethod
    def _get_default_color_space(
        component_type: model.ComponentType,
    ) -> ColorSpace:
        """Return the color family and color space for a model.ComponentType."""

        # NOTE: Assume ACES v1.2 OCIO config.

        color_family = 'Utility'

        default_colorspace = {
            model.ComponentType.BASE_COLOR: 'sRGB - Texture',
            model.ComponentType.SPECULAR_COLOR: 'sRGB - Texture',
            model.ComponentType.TRANSMISSION_COLOR: 'sRGB - Texture',
            model.ComponentType.SUBSURFACE_COLOR: 'sRGB - Texture',
            model.ComponentType.EMISSION_COLOR: 'sRGB - Texture',
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
    node = create_node('arnold::image', parent, hou.VopNode, name)
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


def get_arnold_component(component_type: model.ComponentType) -> str:
    """Return the Arnold component name from a ComponentType."""

    names = {c: c.value for c in model.ComponentType}
    names[model.ComponentType.SPECULAR_IOR] = 'specular_IOR'
    name = names[component_type]
    return name
