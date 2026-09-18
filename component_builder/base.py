import logging
import os.path
from typing import Any, cast

import hou

from . import model, utils

logger = logging.getLogger(__name__)


class ComponentBuilder:
    def __init__(self) -> None:
        pass

    def create_component(
        self, component: model.Component, parent: hou.LopNode | hou.LopNetwork
    ) -> tuple[hou.LopNode, ...]:
        """Create and return all created nodes."""

        all_nodes = []

        output_node = self.create_output(component, parent)
        all_nodes.append(output_node)

        output_position = output_node.position()

        geometry_node = None
        if component.geometry is not None:
            geometry_node = self.create_geometry(component.geometry, parent)
            geometry_node.setPosition(output_position + hou.Vector2(0, 4))
            all_nodes.append(geometry_node)

            output_node.setInput(0, geometry_node)

        if component.material is not None:

            material_library_node = parent.createNode('materiallibrary')
            material_library_node = cast(hou.LopNode, material_library_node)

            # Channel Reference the root prim to the material library
            material_library_node.setParms({'matpathprefix': '/ASSET/mtl/'})
            material_library_node.setPosition(output_position + hou.Vector2(3, 4))
            all_nodes.append(material_library_node)

            self.create_material(component.material, material_library_node)

            if component.material_reference:
                # Replace the Component Material node with a simple reference
                configure_layer_node = parent.createNode('configurelayer')
                configure_layer_node.setParms(
                    {'setsavepath': True, 'savepath': 'mtl.usdc'}
                )
                configure_layer_node.setInput(0, material_library_node)
                configure_layer_node.setPosition(output_position + hou.Vector2(3, 3))

                reference_node = parent.createNode('reference')
                reference_node.setParms({'primpath': '/ASSET'})
                reference_node.setInput(1, configure_layer_node)
                if geometry_node is not None:
                    reference_node.setInput(0, geometry_node)
                reference_node.setPosition(output_position + hou.Vector2(0, 2))
                all_nodes.extend((configure_layer_node, reference_node))

                output_node.setInput(0, reference_node)
                output_node.setParms({'mode': 1})
            else:
                component_material_node = parent.createNode('componentmaterial')
                component_material_node.setInput(1, material_library_node)
                if geometry_node is not None:
                    component_material_node.setInput(0, geometry_node)
                component_material_node.setPosition(output_position + hou.Vector2(0, 2))
                all_nodes.append(component_material_node)

                output_node.setInput(0, component_material_node)

        utils.layout_nodes(all_nodes, margin=hou.Vector2(3, 0))

        output_node.setSelected(True, clear_all_selected=True)

        logger.info(f'Successfully created {component.name!r}')

        return tuple(all_nodes)

    def create_output(
        self, component: model.Component, parent: hou.LopNode | hou.LopNetwork
    ) -> hou.LopNode:
        """Create and return a ComponentOutput node."""

        output_node = parent.createNode('componentoutput', component.name)
        output_node = cast(hou.LopNode, output_node)
        self._set_custom_data(output_node, component.custom_data)
        return output_node

    def create_geometry(
        self, geometry: model.Geometry, parent: hou.LopNode | hou.LopNetwork
    ) -> hou.LopNode:
        """
        Create and return a ComponentGeometry node.

        :raises ValueError: if the file type is not supported.
        """

        component_geometry_node = parent.createNode('componentgeometry')
        assert isinstance(component_geometry_node, hou.LopNode)

        geo_node = component_geometry_node.node('sopnet/geo')
        assert isinstance(geo_node, hou.SopNode), 'invalid node: sopnet/geo'
        default_node = geo_node.node('default')
        assert isinstance(default_node, hou.SopNode), 'invalid node: default'
        proxy_node = geo_node.node('proxy')
        assert isinstance(proxy_node, hou.SopNode), 'invalid node: proxy'

        bottom = default_node.position()

        path = geometry.path.replace('\\', '/')
        filename = os.path.basename(path)
        name, ext = os.path.splitext(filename)

        if ext in ('.fbx', '.obj', '.bgeo', '.sc'):
            file_node = geo_node.createNode('file')
            file_node.setParms({'file': path})
            file_node.setPosition(bottom + hou.Vector2(0, 10))
            output_node = file_node
        elif ext == '.abc':
            alembic_node = geo_node.createNode('alembic')
            alembic_node.setParms({'fileName': path})
            alembic_node.setPosition(bottom + hou.Vector2(0, 12))

            unpack_node = geo_node.createNode('unpack')
            unpack_node.setParms({'limit_iterations': False})
            unpack_node.setPosition(bottom + hou.Vector2(0, 11))
            unpack_node.setInput(0, alembic_node)

            convert_node = geo_node.createNode('convert')
            convert_node.setPosition(bottom + hou.Vector2(0, 10))
            convert_node.setInput(0, unpack_node)
            output_node = convert_node
        else:
            raise ValueError(f'unsupported file extension: {ext}')

        transform_node = geo_node.createNode('xform')
        transform_node.setParms({'scale': geometry.scale})
        transform_node.setPosition(bottom + hou.Vector2(0, 8))
        transform_node.setInput(0, output_node)

        clean_node = geo_node.createNode('clean')
        clean_node.setParms(
            {
                'deldegengeo': False,
                'dodelattribs': True,
                'delattribs': geometry.attributes_keep,
                'dodelgroups': True,
            }
        )
        clean_node.setPosition(bottom + hou.Vector2(0, 6))
        clean_node.setInput(0, transform_node)

        if geometry.proxy is not None:
            bottom = proxy_node.position()

            proxy_clean_node = geo_node.createNode('clean')
            proxy_clean_node.setParms(
                {'deldegengeo': False, 'dodelattribs': True, 'dodelgroups': True}
            )
            proxy_clean_node.setPosition(bottom + hou.Vector2(0, 4))
            proxy_clean_node.setInput(0, clean_node)

            if isinstance(geometry.proxy, model.Geometry.PolyReduceProxy):
                polyreduce_node = geo_node.createNode('polyreduce')
                polyreduce_node.setParms({'percentage': geometry.proxy.percentage})
                polyreduce_node.setPosition(bottom + hou.Vector2(0, 3))
                polyreduce_node.setInput(0, proxy_clean_node)
                proxy_output_node = polyreduce_node
            elif isinstance(geometry.proxy, model.Geometry.BoxProxy):
                bound_node = geo_node.createNode('bound')
                bound_node.setPosition(bottom + hou.Vector2(0, 3))
                bound_node.setInput(0, proxy_clean_node)
                proxy_output_node = bound_node
            elif isinstance(geometry.proxy, model.Geometry.ConvexHullProxy):
                convexhull_node = geo_node.createNode('shrinkwrap')
                convexhull_node.setPosition(bottom + hou.Vector2(0, 3))
                convexhull_node.setInput(0, proxy_clean_node)
                proxy_output_node = convexhull_node
            else:
                proxy_output_node = None

            normal_node = geo_node.createNode('normal')
            normal_node.setParms({'cuspangle': 10})
            normal_node.setPosition(bottom + hou.Vector2(0, 2))
            normal_node.setInput(0, proxy_output_node)

            proxy_node.setInput(0, normal_node)

        default_node.setInput(0, clean_node)

        return component_geometry_node

    def create_material(
        self, material: model.Material, parent: hou.LopNode
    ) -> hou.VopNode:
        """Create and return a Material node."""

        raise NotImplementedError()

    @staticmethod
    def _set_custom_data(node: hou.LopNode, data: dict[str, Any]) -> None:
        """
        Set custom data on a ComponentOutput node.

        :raises ValueError: if `node` is not a ComponentOutput node.
        """

        data_count_parm = node.parm('customdatacount')
        if data_count_parm is None:
            raise ValueError(f'node {node.name()} is not a ComponentOutput node')

        data_count_parm.set(len(data))

        index = 1
        for name, value in data.items():
            name_parm = node.parm(f'customdataname{index}')
            type_parm = node.parm(f'customdatatype{index}')
            if name_parm is None or type_parm is None:
                continue

            if isinstance(value, (tuple, list)):
                value_parm = node.parm(f'customdatastrvalue{index}')
                type_parm.set('stringarray')
                value = ' '.join([str(v) for v in value])
            elif isinstance(value, str):
                value_parm = node.parm(f'customdatastrvalue{index}')
                type_parm.set('string')
            elif isinstance(value, bool):
                value_parm = node.parm(f'customdataboolvalue{index}')
                type_parm.set('bool')
            elif isinstance(value, int):
                value_parm = node.parm(f'customdataintvalue{index}')
                type_parm.set('int')
            elif isinstance(value, float):
                value_parm = node.parm(f'customdatafloatvalue{index}')
                type_parm.set('float')
            else:
                logger.warning(f'Invalid custom data type: {name}: {value}')
                continue

            if value_parm is not None:
                value_parm.set(value)

            index += 1
