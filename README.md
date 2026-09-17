from component_builder.builders.arnold import ComponentType

# Houdini Component Builder

Library for SideFX Houdini to build Solaris Component Builder networks.

![Screenshot](.github/assets/screenshot.png)

## Usage

Build a whole component:

```python
import hou
from component_builder import Component, Geometry, Material, ArnoldComponentBuilder

geometry = Geometry(
    path='/path/to/geo.abc',
    scale=0.01,
    proxy=Geometry.ConvexHullProxy()
)

material = Material(
    name='base',
    values={Material.ComponentType.SPECULAR_IOR: 1.4},
    textures={
        Material.ComponentType.BASE_COLOR: Material.TextureMap('base_color.jpg'),
        Material.ComponentType.NORMAL: Material.TextureMap('normal.jpg'),
        Material.ComponentType.SPECULAR_ROUGHNESS: Material.TextureMap('roughness.jpg'),
        Material.ComponentType.DISPLACEMENT: Material.TextureMap('displacement.exr')
    },
    triplanar=True,
    triplanar_scale=hou.Vector3(2.1, 0.5, 0.7)
)

component = Component(
    name='table',
    geometry=geometry,
    material=material,
)

builder = ArnoldComponentBuilder()
builder.create_component(component, hou.node('/stage'))
```

## License

Copyright (c) 2026 Beat Reichenbach. This project is licensed under the [GPLv3 License](LICENSE).
