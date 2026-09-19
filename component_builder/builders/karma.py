import logging

import hou
import voptoolutils

from .. import base, model, utils
from ..exceptions import ComponentBuilderError

logger = logging.getLogger(__name__)


class KarmaComponentBuilder(base.ComponentBuilder):
    def post_geometry(
        self,
        geometry: model.Geometry,
        parent: hou.LopNode | hou.LopNetwork,
        geometry_node: hou.LopNode,
    ) -> tuple[hou.LopNode, ...]:
        created_nodes: list[hou.LopNode] = []

        anchor_position = geometry_node.position()

        # Render Geometry Settings
        settings_node = create_render_geometry_settings(parent)
        settings_node.setPosition(anchor_position + hou.Vector2(0, -1))
        settings_node.setInput(0, geometry_node)
        created_nodes.append(settings_node)

        return tuple(created_nodes)

    def create_material(
        self, material: model.Material, parent: hou.LopNode
    ) -> hou.VopNode:
        builder = create_karma_material_builder(parent, material.name)

        # Standard Surface
        surface_name = 'mtlxstandard_surface'
        surface_node = builder.node(surface_name)
        if surface_node is None:
            raise ComponentBuilderError(f'missing child node: {surface_name!r}')

        # Displacement
        displacement_name = 'mtlxdisplacement'
        displacement_node = builder.node(displacement_name)
        if displacement_node is None:
            raise ComponentBuilderError(f'missing child node: {displacement_name!r}')

        # Values
        if material.thin_walled:
            surface_node.setParms({'thin_walled': True})
        values = {get_karma_component(c): v for c, v in material.values.items()}
        surface_node.setParms(values)

        # Textures
        for component_type, texture in material.textures.items():
            if not texture.path:
                logger.warning(f'Empty texture path for component: {component_type}')
                continue

            name = f'image_{component_type}'

            # Displacement
            if component_type == model.ComponentType.DISPLACEMENT:
                if material.triplanar:
                    triplanar_node = create_triplanar(
                        parent=builder,
                        scale=material.triplanar_scale,
                        filename=texture.path,
                    )
                    tail = triplanar_node
                else:
                    image_node = create_image(
                        parent=builder,
                        name=name,
                        filename=texture.path,
                        color_space=texture.color_space,
                    )
                    tail = image_node

                displacement_node.setInput(0, tail)
                continue

            component_name = get_karma_component(component_type)
            index = surface_node.inputIndex(component_name)
            if index < 0:
                logger.warning(f'Invalid channel for StandardSurface: {component_type}')
                continue

            # Channels
            if material.triplanar:
                triplanar_node = create_triplanar(
                    parent=builder,
                    scale=material.triplanar_scale,
                    filename=texture.path,
                )
                tail = triplanar_node
            else:
                image_node = create_image(
                    parent=builder,
                    name=name,
                    filename=texture.path,
                    color_space=texture.color_space,
                )
                tail = image_node

            # Normal Map
            if component_type == model.ComponentType.NORMAL:
                normal_map_node = utils.create_node(
                    'mtlxnormalmap', builder, hou.VopNode
                )
                normal_map_node.setInput(0, tail)
                tail = normal_map_node

            surface_node.setInput(index, tail)

        builder.layoutChildren()

        return builder


def create_image(
    parent: hou.VopNode,
    name: str | None = None,
    filename: str = '',
    color_space: str = '',
) -> hou.VopNode:
    """Create and return an image node."""

    filename = filename.replace('\\', '/')
    node = utils.create_node('mtlximage', parent, hou.VopNode, name)
    node.setParms({'file': filename, 'filecolorspace': color_space})

    return node


def create_triplanar(
    parent: hou.VopNode, name: str | None = None, scale: float = 1, filename: str = ''
) -> hou.VopNode:
    """Create and return a Triplanar node."""

    node = utils.create_node('kma_hextiled_triplanar', parent, hou.VopNode, name)
    filename = filename.replace('\\', '/')
    node.setParms({'file': filename, 'scale': scale})
    return node


def create_render_geometry_settings(
    parent: hou.LopNode | hou.LopNetwork, name: str | None = None
) -> hou.LopNode:
    """Create and return a RenderGeometrySettings node."""

    node = utils.create_node('rendergeometrysettings', parent, hou.LopNode, name)

    # NOTE: Set most parameters to default values to make it easier for the user to
    # start setting custom values.
    values = {
        'primpattern': f'{base.ROOT_PRIM}/geo/*',
        hou.text.encode('primvars:karma:object:dicingquality_control'): 'set',
        hou.text.encode('primvars:karma:object:truedisplace_control'): 'set',
        hou.text.encode('primvars:karma:object:dicingdepthmin_control'): 'set',
        hou.text.encode('primvars:karma:object:dicingdepthmax_control'): 'set',
    }
    node.setParms(values)

    return node


def get_karma_component(component_type: model.ComponentType) -> str:
    """Return the Karma component name from a ComponentType."""

    names = {c: c.value for c in model.ComponentType}
    names[model.ComponentType.SPECULAR_IOR] = 'specular_IOR'
    name = names[component_type]
    return name


def create_karma_material_builder(
    parent: hou.LopNode, name: str | None = None
) -> hou.VopNode:
    mask = voptoolutils.KARMAMTLX_TAB_MASK

    builder = parent.createNode('subnet', name, force_valid_node_name=True)
    material_node = voptoolutils._setupMtlXBuilderSubnet(
        subnet_node=builder,
        destination_node='karmamaterial',
        name='karmamaterial',
        mask=mask,
        folder_label='Karma Material Builder',
        render_context='kma',
    )

    return material_node
