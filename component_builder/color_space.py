from enum import StrEnum
from typing import NamedTuple

import PyOpenColorIO as ocio

from .model import ComponentType


class ColorSpaceName(StrEnum):
    """Color Space Names provided by Houdini."""

    SRGB_TEXTURE = 'srgb_texture'
    LIN_REC709 = 'lin_rec709'
    G22_REC709 = 'g22_rec709'
    G18_REC709 = 'g18_rec709'
    ACESCG = 'acescg'
    LIN_AP1 = 'lin_ap1'
    LIN_SRGB = 'lin_srgb'
    G22_AP1 = 'g22_ap1'
    G18_AP1 = 'g18_ap1'
    ADOBE_RGB = 'adobergb'
    LIN_ADOBE_RGB = 'lin_adobergb'
    SRGB_DISPLAY_P3 = 'srgb_displayp3'
    LIN_DISPLAY_P3 = 'lin_displayp3'
    RAW = 'raw'


class ColorSpace(NamedTuple):
    color_family: str
    color_space: str


_COLOR_COMPONENT_TYPES = frozenset(
    {
        ComponentType.BASE_COLOR,
        ComponentType.SPECULAR_COLOR,
        ComponentType.TRANSMISSION_COLOR,
        ComponentType.SUBSURFACE_COLOR,
        ComponentType.EMISSION_COLOR,
    }
)


def get_color_space(name: str) -> ColorSpace | None:
    """Return the OCIO family and name for a color-space name."""

    if not name:
        return None

    config = ocio.GetCurrentConfig()
    color_space = _get_color_space(config, name)
    if color_space is None:
        return None

    return ColorSpace(color_space.getFamily(), color_space.getName())


def get_default_color_space_name(component_type: ComponentType) -> str:
    """Return the default color-space name for a component type."""

    if component_type in _COLOR_COMPONENT_TYPES:
        return str(ColorSpaceName.SRGB_TEXTURE)

    return str(ColorSpaceName.RAW)


def _get_color_space(config: ocio.Config, name: str) -> ocio.ColorSpace | None:
    color_space = config.getColorSpace(name)
    if color_space is None:
        return None

    return _get_canonical_color_space(config, color_space)


def _get_canonical_color_space(
    config: ocio.Config, color_space: ocio.ColorSpace
) -> ocio.ColorSpace:
    """Return the canonical OCIO color space for an alias."""

    root_family = color_space.getFamily().split('/', 1)[0]
    equality_group = color_space.getEqualityGroup()

    if equality_group:
        for name in config.getColorSpaceNames():
            candidate = config.getColorSpace(name)
            if candidate is None:
                continue

            if (
                candidate.getFamily() == root_family
                and candidate.getEqualityGroup() == equality_group
            ):
                return candidate

    directions = (
        ocio.ColorSpaceDirection.COLORSPACE_DIR_TO_REFERENCE,
        ocio.ColorSpaceDirection.COLORSPACE_DIR_FROM_REFERENCE,
    )
    for direction in directions:
        transform = color_space.getTransform(direction)
        if not isinstance(transform, ocio.ColorSpaceTransform):
            continue

        if direction == ocio.ColorSpaceDirection.COLORSPACE_DIR_TO_REFERENCE:
            candidate_name = transform.getSrc()
        else:
            candidate_name = transform.getDst()

        candidate = config.getColorSpace(candidate_name)
        if candidate is not None and candidate.getName() != color_space.getName():
            return candidate

    return color_space
