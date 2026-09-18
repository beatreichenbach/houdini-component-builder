import logging
from abc import ABC, abstractmethod
from typing import Any, cast

import hou

from . import model, utils
from .exceptions import ComponentBuilderError

logger = logging.getLogger(__name__)

ROOT_PRIM = '/ASSET'

GEO_FORMATS = ('.bgeo.sc', '.bgeo.gz', '.bgeo', '.geo', '.obj', '.fbx')
ALEMBIC_FORMATS = ('.abc',)
USD_FORMATS = ('.usd', '.usda', '.usdc', '.usdz')


class ComponentBuilder(ABC):
    def create_component(
        self, component: model.Component, parent: hou.LopNode | hou.LopNetwork
    ) -> tuple[hou.LopNode, ...]:
        """
        Create and return all created nodes.

        :raises ComponentBuilderError: if the creation failed.
        """

        all_nodes = []
        anchor_position = hou.Vector2(0, 0)
        tail: hou.LopNode | None = None

        # Geometry
        if component.geometry is not None:
            geometry_node = self.create_geometry(component.geometry, parent)
            geometry_node.setPosition(anchor_position)
            anchor_position = geometry_node.position()
            all_nodes.append(geometry_node)
            tail = geometry_node

            inserted_nodes = self.post_geometry(
                component.geometry, geometry_node, parent
            )
            all_nodes.extend(inserted_nodes)
            if inserted_nodes:
                anchor_position = inserted_nodes[-1].position()
                tail = inserted_nodes[-1]

        # Material
        if component.material is not None:
            material_library_node = parent.createNode('materiallibrary')
            material_library_node = cast(hou.LopNode, material_library_node)
            material_library_node.setParms({'matpathprefix': f'{ROOT_PRIM}/mtl/'})
            material_library_node.setPosition(anchor_position + hou.Vector2(3, 0))
            all_nodes.append(material_library_node)

            self.create_material(component.material, material_library_node)

            if component.material_reference:
                # Replace the Component Material node with a simple reference
                configure_layer_node = parent.createNode('configurelayer')
                configure_layer_node.setParms(
                    {'setsavepath': True, 'savepath': 'mtl.usdc'}
                )
                configure_layer_node.setInput(0, material_library_node)
                configure_layer_node.setPosition(anchor_position + hou.Vector2(3, -1))

                reference_node = parent.createNode('reference')
                reference_node = cast(hou.LopNode, reference_node)
                reference_node.setParms({'primpath': ROOT_PRIM})
                reference_node.setInput(1, configure_layer_node)
                reference_node.setPosition(anchor_position + hou.Vector2(0, -2))
                if tail is not None:
                    reference_node.setInput(0, tail)
                all_nodes.extend((configure_layer_node, reference_node))
                anchor_position = reference_node.position()
                tail = reference_node
            else:
                component_material_node = parent.createNode('componentmaterial')
                component_material_node = cast(hou.LopNode, component_material_node)
                component_material_node.setInput(1, material_library_node)
                component_material_node.setPosition(
                    anchor_position + hou.Vector2(0, -2)
                )
                if tail is not None:
                    component_material_node.setInput(0, tail)
                all_nodes.append(component_material_node)
                anchor_position = component_material_node.position()
                tail = component_material_node

        # Output
        output_node = self.create_output(component, parent)
        if component.material_reference:
            output_node.setParms({'mode': 1})
        output_node.setInput(0, tail)
        output_node.setPosition(anchor_position + hou.Vector2(0, -2))
        output_node.setSelected(True, clear_all_selected=True)
        all_nodes.append(output_node)

        logger.info(f'Successfully created {component.name!r}')

        utils.layout_nodes(all_nodes, margin=hou.Vector2(3, 0))

        return tuple(all_nodes)

    def create_output(
        self, component: model.Component, parent: hou.LopNode | hou.LopNetwork
    ) -> hou.LopNode:
        """Create and return a ComponentOutput node."""

        output_node = parent.createNode(
            'componentoutput', component.name, force_valid_node_name=True
        )
        output_node = cast(hou.LopNode, output_node)
        self._set_custom_data(output_node, component.custom_data)
        return output_node

    def pre_output(
        self,
        component: model.Component,
        output_node: hou.LopNode,
        parent: hou.LopNode | hou.LopNetwork,
    ) -> tuple[hou.LopNode, ...]:
        """
        Create and return nodes that are inserted before the ComponentOutput node.
        """

        return ()

    def create_geometry(
        self, geometry: model.Geometry, parent: hou.LopNode | hou.LopNetwork
    ) -> hou.LopNode:
        """
        Create and return a ComponentGeometry node.

        :raises ComponentBuilderError: if the creation failed.
        """

        component_geometry_node = parent.createNode('componentgeometry')
        component_geometry_node = cast(hou.LopNode, component_geometry_node)

        geo_node_name = 'sopnet/geo'
        geo_node = component_geometry_node.node(geo_node_name)
        if geo_node is None:
            raise ComponentBuilderError(f'missing node: {geo_node_name!r}')
        geo_node = cast(hou.SopNode, cast(hou.OpNode, geo_node))

        default_node_name = 'default'
        default_node = geo_node.node(default_node_name)
        if default_node is None:
            raise ComponentBuilderError(f'missing node: {default_node_name!r}')

        proxy_node_name = 'proxy'
        proxy_node = geo_node.node(proxy_node_name)
        if proxy_node is None:
            raise ComponentBuilderError(f'missing node: {proxy_node_name!r}')

        bottom = default_node.position()

        path = geometry.path.replace('\\', '/')
        if path.endswith(GEO_FORMATS):
            file_node = geo_node.createNode('file')
            file_node.setParms({'file': path})
            file_node.setPosition(bottom + hou.Vector2(0, 10))
            output_node = file_node
        elif path.endswith(ALEMBIC_FORMATS):
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
        elif path.endswith(USD_FORMATS):
            usd_import_node = geo_node.createNode('usdimport')
            usd_import_node.setParms(
                {
                    'filepath1': path,
                    'input_unpack': True,
                    'unpack_geomtype': 1,  # Polygons
                }
            )
            import_time_parm = usd_import_node.parm('importtime')
            if import_time_parm is not None:
                import_time_parm.deleteAllKeyframes()
            usd_import_node.setPosition(bottom + hou.Vector2(0, 10))
            output_node = usd_import_node
        else:
            raise ComponentBuilderError(f'unsupported file type: {path!r}')

        transform_node = geo_node.createNode('xform')
        transform_node.setParms({'scale': geometry.scale})
        transform_node.setPosition(bottom + hou.Vector2(0, 8))
        transform_node.setInput(0, output_node)

        clean_node = geo_node.createNode('clean')
        clean_node.setParms(
            {
                'deldegengeo': False,
                'dodelattribs': True,
                'delattribs': geometry.delete_attributes,
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

            proxy_output_node: hou.SopNode | None = None
            match geometry.proxy:
                case model.PolyReduceProxy():
                    polyreduce_node = geo_node.createNode('polyreduce')
                    polyreduce_node.setParms({'percentage': geometry.proxy.percentage})
                    polyreduce_node.setPosition(bottom + hou.Vector2(0, 3))
                    polyreduce_node.setInput(0, proxy_clean_node)
                    proxy_output_node = polyreduce_node
                case model.BoxProxy():
                    bound_node = geo_node.createNode('bound')
                    bound_node.setPosition(bottom + hou.Vector2(0, 3))
                    bound_node.setInput(0, proxy_clean_node)
                    proxy_output_node = bound_node
                case model.ConvexHullProxy():
                    convexhull_node = geo_node.createNode('shrinkwrap')
                    convexhull_node.setPosition(bottom + hou.Vector2(0, 3))
                    convexhull_node.setInput(0, proxy_clean_node)
                    proxy_output_node = convexhull_node
                case _:
                    raise ComponentBuilderError(
                        f'unsupported proxy type: {type(geometry.proxy).__name__}'
                    )

            normal_node = geo_node.createNode('normal')
            normal_node.setParms({'cuspangle': 10})
            normal_node.setPosition(bottom + hou.Vector2(0, 2))
            normal_node.setInput(0, proxy_output_node)

            proxy_node.setInput(0, normal_node)

        default_node.setInput(0, clean_node)

        return component_geometry_node

    def post_geometry(
        self,
        geometry: model.Geometry,
        geometry_node: hou.LopNode,
        parent: hou.LopNode | hou.LopNetwork,
    ) -> tuple[hou.LopNode, ...]:
        """
        Create and return nodes that are inserted after the ComponentGeometry node.
        """

        return ()

    @abstractmethod
    def create_material(
        self, material: model.Material, parent: hou.LopNode
    ) -> hou.VopNode:
        """Create and return a Material node.

        :raises ComponentBuilderError: if the creation failed.
        """

    @staticmethod
    def _set_custom_data(node: hou.LopNode, data: dict[str, Any]) -> None:
        """Set custom data on a ComponentOutput node."""

        # Filter valid data
        parm_data = {}
        for name, value in data.items():
            if isinstance(value, (tuple, list)):
                parm_name = 'customdatastrvalue'
                data_type = 'stringarray'
                value = ' '.join([str(v) for v in value])
            elif isinstance(value, str):
                parm_name = 'customdatastrvalue'
                data_type = 'string'
            elif isinstance(value, bool):
                parm_name = 'customdataboolvalue'
                data_type = 'bool'
            elif isinstance(value, int):
                parm_name = 'customdataintvalue'
                data_type = 'int'
            elif isinstance(value, float):
                parm_name = 'customdatafloatvalue'
                data_type = 'float'
            else:
                logger.warning(f'Invalid custom data type: {name}: {value}')
                continue
            parm_data[name] = (parm_name, data_type, value)

        # Populate custom data
        data_count_parm = node.parm('customdatacount')
        if data_count_parm is None:
            return

        data_count_parm.set(len(parm_data))
        index = 1
        for name, (parm_name, data_type, value) in parm_data.items():
            name_parm = node.parm(f'customdataname{index}')
            type_parm = node.parm(f'customdatatype{index}')
            value_parm = node.parm(f'{parm_name}{index}')

            if name_parm is None or type_parm is None or value_parm is None:
                continue

            name_parm.set(name)
            type_parm.set(data_type)
            value_parm.set(value)
            index += 1
