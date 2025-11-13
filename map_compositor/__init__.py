# !/usr/bin/python
# coding=utf-8
from pythontk.core_utils.module_resolver import bootstrap_package

__package__ = "map_compositor"
__version__ = "0.5.16"


DEFAULT_INCLUDE = {
    "_map_compositor": [
        "MapCompositorSignals",
        "MapCompositor",
        "MapCompositorSlots",
        "MapCompositorUI",
    ]
}


bootstrap_package(
    globals(),
    include=DEFAULT_INCLUDE,
)


__all__ = [
    "MapCompositorSignals",
    "MapCompositor",
    "MapCompositorSlots",
    "MapCompositorUI",
    "__version__",
]
