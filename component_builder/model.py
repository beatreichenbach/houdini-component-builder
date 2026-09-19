import dataclasses
from enum import StrEnum
from typing import Any


# Geometry
class Proxy: ...


class ConvexHullProxy(Proxy): ...


class BoxProxy(Proxy): ...


@dataclasses.dataclass
class PolyReduceProxy(Proxy):
    percentage: float = 10


@dataclasses.dataclass
class Geometry:
    path: str
    scale: float = 1.0
    delete_attributes: str = '* ^N ^uv'
    proxy: Proxy | None = None


# Material
class ComponentType(StrEnum):
    BASE = 'base'
    BASE_COLOR = 'base_color'
    METALNESS = 'metalness'
    SPECULAR_COLOR = 'specular_color'
    SPECULAR_ROUGHNESS = 'specular_roughness'
    SPECULAR_IOR = 'specular_ior'
    TRANSMISSION = 'transmission'
    TRANSMISSION_COLOR = 'transmission_color'
    SUBSURFACE = 'subsurface'
    SUBSURFACE_COLOR = 'subsurface_color'
    EMISSION = 'emission'
    EMISSION_COLOR = 'emission_color'
    OPACITY = 'opacity'
    NORMAL = 'normal'
    DISPLACEMENT = 'displacement'


@dataclasses.dataclass
class TextureMap:
    path: str
    color_space: str = ''


@dataclasses.dataclass
class Material:
    name: str
    values: dict[ComponentType, Any] = dataclasses.field(default_factory=dict)
    textures: dict[ComponentType, TextureMap] = dataclasses.field(default_factory=dict)
    triplanar: bool = False
    triplanar_scale: tuple[float, float, float] = (1, 1, 1)
    thin_walled: bool = False


# Output
@dataclasses.dataclass
class Component:
    name: str
    geometry: Geometry | None = None
    material: Material | None = None
    material_reference: bool = True
    custom_data: dict[str, Any] = dataclasses.field(default_factory=dict)
