# coding=utf-8
"""Layer filtering tests.

Covers the regression where ``QgsLayerTreeLayer.layer()`` returned ``None``
(unresolved/broken layer nodes) and aborted the plugin with
``AttributeError: 'NoneType' object has no attribute 'type'``.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

import unittest
from unittest import mock

try:
    import qgis.core  # noqa: F401  # probe for the QGIS bindings

    import vector_batch_saver as vbs_module
    from vector_batch_saver import VectorBatchSaver

    QGIS_AVAILABLE = True
    QGIS_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - depends on local QGIS install
    QGIS_AVAILABLE = False
    QGIS_IMPORT_ERROR = str(exc)

if not QGIS_AVAILABLE:  # pragma: no cover - fallback for package-style imports
    try:
        import os
        import sys

        sys.path.insert(
            0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        from vector_batch_saver.vector_batch_saver import VectorBatchSaver
        from vector_batch_saver import vector_batch_saver as vbs_module

        QGIS_AVAILABLE = True
    except Exception as exc:  # pragma: no cover
        QGIS_IMPORT_ERROR = str(exc)

if QGIS_AVAILABLE:  # pragma: no cover - constants depend on the bindings
    VECTOR_LAYER_TYPE = VectorBatchSaver.VECTOR_LAYER_TYPE
    # Any value that is not the vector layer type; keeps the tests
    # independent of which enum layout the running QGIS exposes.
    OTHER_LAYER_TYPE = object()


class _FakeLayer:
    """Minimal stand-in for a QgsMapLayer."""

    def __init__(self, layer_type, layer_id="layer-id"):
        self._layer_type = layer_type
        self._layer_id = layer_id

    def type(self):
        return self._layer_type

    def id(self):
        return self._layer_id

    def name(self):
        return self._layer_id


class _DeletedLayer:
    """Simulates a layer whose C++ object was already deleted."""

    def type(self):
        raise RuntimeError(
            "wrapped C/C++ object of type QgsVectorLayer has been deleted"
        )

    def id(self):
        raise RuntimeError(
            "wrapped C/C++ object of type QgsVectorLayer has been deleted"
        )


class _FakeTreeLayer:
    def __init__(self, layer, name="", layer_id=""):
        self._layer = layer
        self._name = name
        self._layer_id = layer_id or self._safe_layer_id(layer)

    @staticmethod
    def _safe_layer_id(layer):
        try:
            return layer.id() if layer is not None else ""
        except (AttributeError, RuntimeError):
            return ""

    def layer(self):
        return self._layer

    def layerId(self):
        return self._layer_id

    def name(self):
        return self._name or self._layer_id


class _BrokenTreeLayer:
    """Layer-tree node whose layer is gone and whose id is not registered."""

    def __init__(self, name):
        self._name = name

    def layer(self):
        return None

    def layerId(self):
        return "missing-" + self._name

    def name(self):
        return self._name


class _FakeRoot:
    def __init__(self, tree_layers):
        self._tree_layers = tree_layers

    def findLayers(self):
        return list(self._tree_layers)


class _FakeProject:
    """Project stub exposing only the registry lookup used by the plugin."""

    def __init__(self, root, layers=()):
        self._root = root
        self._layers = {layer.id(): layer for layer in layers}

    def layerTreeRoot(self):
        return self._root

    def mapLayer(self, layer_id):
        return self._layers.get(layer_id)


class _FakeMessageBar:
    def __init__(self):
        self.messages = []

    def pushMessage(self, title, text, level=None, duration=None):
        self.messages.append({"title": title, "text": text, "level": level})


class _FakeIface:
    def __init__(self):
        self._message_bar = _FakeMessageBar()

    def messageBar(self):
        return self._message_bar


@unittest.skipUnless(
    QGIS_AVAILABLE, "QGIS bindings unavailable: " + QGIS_IMPORT_ERROR
)
class VectorBatchSaverLayerFilterTest(unittest.TestCase):
    """Vector layer detection must tolerate broken layer tree nodes."""

    def setUp(self):
        self.plugin = object.__new__(VectorBatchSaver)

    def _patch_project(self, project):
        patcher = mock.patch.object(vbs_module, "QgsProject")
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        mocked.instance.return_value = project
        return mocked

    def test_none_layer_is_not_vector(self):
        self.assertFalse(VectorBatchSaver.is_vector_layer(None))

    def test_deleted_layer_is_not_vector(self):
        self.assertFalse(VectorBatchSaver.is_vector_layer(_DeletedLayer()))

    def test_object_without_type_is_not_vector(self):
        self.assertFalse(VectorBatchSaver.is_vector_layer(object()))

    def test_vector_layer_is_vector(self):
        layer = _FakeLayer(VECTOR_LAYER_TYPE)
        self.assertTrue(VectorBatchSaver.is_vector_layer(layer))

    def test_raster_layer_is_not_vector(self):
        layer = _FakeLayer(OTHER_LAYER_TYPE)
        self.assertFalse(VectorBatchSaver.is_vector_layer(layer))

    def test_broken_nodes_are_skipped_and_reported(self):
        vector_layer = _FakeLayer(VECTOR_LAYER_TYPE, "vector")
        raster_layer = _FakeLayer(OTHER_LAYER_TYPE, "raster")
        root = _FakeRoot(
            [
                _FakeTreeLayer(vector_layer),
                _FakeTreeLayer(raster_layer),
                _BrokenTreeLayer("roads"),
                _FakeTreeLayer(_DeletedLayer(), name="deleted"),
            ]
        )
        self._patch_project(_FakeProject(root, [vector_layer, raster_layer]))

        vector_layers, skipped = self.plugin.project_vector_layers_report()

        self.assertEqual(vector_layers, [vector_layer])
        self.assertEqual(skipped, ["roads", "deleted"])

    def test_registry_lookup_avoids_dangling_layer(self):
        """A node whose layer() is dead but whose id is registered works."""
        layer = _FakeLayer(VECTOR_LAYER_TYPE, "registered")
        node = _FakeTreeLayer(
            _DeletedLayer(), name="registered", layer_id="registered"
        )
        self._patch_project(_FakeProject(_FakeRoot([node]), [layer]))

        self.assertEqual(self.plugin.project_vector_layers(), [layer])

    def test_dangling_node_without_registry_entry_is_skipped(self):
        node = _FakeTreeLayer(_DeletedLayer(), name="orphan", layer_id="orphan")
        self._patch_project(_FakeProject(_FakeRoot([node]), []))

        self.assertEqual(self.plugin.project_vector_layers(), [])

    def test_duplicate_nodes_are_reported_once(self):
        layer = _FakeLayer(VECTOR_LAYER_TYPE, "dup")
        root = _FakeRoot(
            [
                _FakeTreeLayer(layer),
                _FakeTreeLayer(layer),
                _BrokenTreeLayer("broken"),
                _BrokenTreeLayer("broken"),
            ]
        )
        self._patch_project(_FakeProject(root, [layer]))

        vector_layers, skipped = self.plugin.project_vector_layers_report()

        self.assertEqual(len(vector_layers), 1)
        self.assertEqual(skipped, ["broken"])

    def test_project_vector_layers_without_project_root(self):
        self._patch_project(_FakeProject(None))
        self.assertEqual(self.plugin.project_vector_layers(), [])

    def test_notify_skipped_layers_truncates_long_lists(self):
        self.plugin.iface = _FakeIface()
        names = ["layer{0}".format(index) for index in range(7)]

        self.plugin.notify_skipped_layers(names)

        messages = self.plugin.iface.messageBar().messages
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]["title"], "Unavailable layers skipped")
        self.assertIn("7 layer(s)", messages[0]["text"])
        self.assertIn("layer0, layer1", messages[0]["text"])
        self.assertNotIn("layer6", messages[0]["text"])
        self.assertTrue(messages[0]["text"].endswith(", ..."))

    def test_notify_skipped_layers_without_iface_is_safe(self):
        self.plugin.iface = None
        self.plugin.notify_skipped_layers(["broken"])


class _EnumScope:
    """Scoped enum container, e.g. ``Qgis.MessageLevel``."""

    Info = 3
    NoError = 0


class _ScopedEnumOwner:
    MessageLevel = _EnumScope
    WriterError = _EnumScope


class _FlatEnumOwner:
    """Legacy QGIS 3 style: enum members directly on the class."""

    Info = 3
    NoError = 0


@unittest.skipUnless(
    QGIS_AVAILABLE, "QGIS bindings unavailable: " + QGIS_IMPORT_ERROR
)
class ScopedEnumTest(unittest.TestCase):
    """Qt6 compatibility: scoped enums first, flat legacy names second."""

    def test_scoped_enum_uses_scoped_form(self):
        value = vbs_module.scoped_enum((_ScopedEnumOwner, "MessageLevel", "Info"))
        self.assertEqual(value, 3)

    def test_scoped_enum_falls_back_to_flat_member(self):
        value = vbs_module.scoped_enum((_FlatEnumOwner, "MessageLevel", "Info"))
        self.assertEqual(value, 3)

    def test_scoped_enum_supports_plain_attribute(self):
        value = vbs_module.scoped_enum((_FlatEnumOwner, None, "Info"))
        self.assertEqual(value, 3)

    def test_scoped_enum_keeps_zero_members(self):
        value = vbs_module.scoped_enum((_ScopedEnumOwner, "WriterError", "NoError"))
        self.assertEqual(value, 0)

    def test_scoped_enum_skips_none_owner(self):
        value = vbs_module.scoped_enum(
            (None, "MessageLevel", "Info"),
            (_FlatEnumOwner, "MessageLevel", "Info"),
        )
        self.assertEqual(value, 3)

    def test_scoped_enum_raises_when_unresolvable(self):
        with self.assertRaises(AttributeError):
            vbs_module.scoped_enum((object(), "MessageLevel", "Info"))


if __name__ == "__main__":
    unittest.main()
