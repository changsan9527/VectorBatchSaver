# coding=utf-8
"""Icon file test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'changsan9527@gmail.com'
__date__ = '2026-07-05'
__copyright__ = 'Copyright 2026, changsan9527'

import os
import unittest

from qgis.PyQt.QtGui import QIcon



class VectorBatchSaverResourcesTest(unittest.TestCase):
    """Test icon asset loads."""

    def setUp(self):
        """Runs before each test."""
        pass

    def tearDown(self):
        """Runs after each test."""
        pass

    def test_icon_png(self):
        """Test the plugin icon asset loads."""
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'icon.svg',
        )
        icon = QIcon(path)
        self.assertFalse(icon.isNull())

if __name__ == "__main__":
    suite = unittest.makeSuite(VectorBatchSaverResourcesTest)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)



