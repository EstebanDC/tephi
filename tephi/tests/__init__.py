"""
Provides enhanced testing capabilities.

The primary class for this module is :class:`MontyTest`.

When importing this module, sys.argv is inspected to identify the flags
``-d`` and ``-sf`` which toggle displaying and saving image tests respectively.

.. note:: The ``-d`` option sets the matplotlib backend to either agg or
    tkagg. For this reason ``monty.tests`` **must** be imported before
    ``matplotlib.pyplot``

"""

import collections
import contextlib
import difflib
import logging
import os
import os.path
import platform
import StringIO
import sys
import tempfile
import unittest
import zlib

import matplotlib
# NB pyplot is imported after main() so that a backend can be defined.
# import matplotlib.pyplot as plt
import numpy


_DATA_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'data')
"""Basepath for test data."""

_RESULT_PATH = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'results')
"""Basepath for test results."""


# A shared logger for use by unit tests
logging.basicConfig()
logger = logging.getLogger('tests')


# Whether to display matplotlib output to the screen.
_DISPLAY_FIGURES = False

# Whether to save matplotlib output to files.
_SAVE_FIGURES = True

if '-d' in sys.argv:
    sys.argv.remove('-d')
    matplotlib.use('tkagg')
    _DISPLAY_FIGURES = True
else:
    matplotlib.use('agg')

# Imported now so that matplotlib.use can work 
import matplotlib.pyplot as plt

if '-sf' in sys.argv or os.environ.get('MONTY_TEST_SAVE_FIGURES', '') == '1':
    if '-sf' in sys.argv:
        sys.argv.remove('-sf')
    _SAVE_FIGURES = True


_PLATFORM = '%s_%s' % (''.join(platform.dist()[:2]), platform.architecture()[0])


def main():
    """
    A wrapper for unittest.main() which adds customised options to the
    help (-h) output.
    
    """
    if '-h' in sys.argv or '--help' in sys.argv:
        stdout = sys.stdout
        buff = StringIO.StringIO()
        # NB. unittest.main() raises an exception after it's shown the help text
        try:
            sys.stdout = buff
            unittest.main()
        finally:
            sys.stdout = stdout
            lines = buff.getvalue().split('\n')
            lines.insert(9, 'Monty-specific options:')
            lines.insert(10, '  -d                   Display matplotlib figures (uses tkagg)')
            lines.insert(11, '  -sf                  Save matplotlib figures to subfolder "image_results"')
            print '\n'.join(lines)
    else:
        unittest.main()


def get_data_path(relative_path):
    """
    Returns the absolute path to a data file when given the relative path
    as a string, or sequence of strings.
    
    """
    if not isinstance(relative_path, basestring):
        relative_path = os.path.join(*relative_path)
    return os.path.abspath(os.path.join(_DATA_PATH, relative_path))


def get_result_path(relative_path):
    """
    Returns the absolute path to a result file when given the relative path
    as a string, or sequence of strings.
    
    """
    if not isinstance(relative_path, basestring):
        relative_path = os.path.join(*relative_path)
    return os.path.abspath(os.path.join(_RESULT_PATH, relative_path))


class MontyTest(unittest.TestCase):
    """
    A subclass of unittest.TestCase which provides testing functionality
    specific to Monty.
    
    """

    _assertion_counts = collections.defaultdict(int)

    def file_checksum(self, file_path):
        """
        Generate checksum from file.
        """
        in_file = open(file_path, "rb")
        return zlib.crc32(in_file.read())
    
    def _unique_id(self):
        """
        Returns the unique ID for the current assertion.

        The ID is composed of two parts: a unique ID for the current test
        (which is itself composed of the module, class, and test names), and
        a sequential counter (specific to the current test) that is incremented
        on each call.

        For example, calls from a "test_tx" routine followed by a "test_ty"
        routine might result in::
            test_plot.TestContourf.test_tx.0
            test_plot.TestContourf.test_tx.1
            test_plot.TestContourf.test_tx.2
            test_plot.TestContourf.test_ty.0

        """
        # Obtain a consistent ID for the current test.
        
        # NB. unittest.TestCase.id() returns different values depending on
        # whether the test has been run explicitly, or via test discovery.
        # For example:
        #   python tests/test_brand.py
        #       => '__main__.TestBranding.test_combo'
        #   python -m unittest discover
        #       => 'monty.tests.test_brand.TestBranding.test_combo'
        bits = self.id().split('.')[-3:]
        if bits[0] == '__main__':
            file_name = os.path.basename(sys.modules['__main__'].__file__)
            bits[0] = os.path.splitext(file_name)[0]
        test_id = '.'.join(bits)

        # Derive the sequential assertion ID within the test
        assertion_id = self._assertion_counts[test_id]
        self._assertion_counts[test_id] += 1
        
        return test_id + '.' + str(assertion_id)
    
    def _ensure_folder(self, path):
        dir_path = os.path.dirname(path)
        if not os.path.exists(dir_path):
            logger.warning('Creating folder: %s', dir_path)
            os.makedirs(dir_path)
    
    def create_temp_filename(self, suffix=''):
        """
        Return a temporary file name.

        Args:

        * suffix  -  Optional filename extension.

        """
        temp_file = tempfile.mkstemp(suffix)
        os.close(temp_file[0])
        return temp_file[1]

    @contextlib.contextmanager
    def temp_filename(self, suffix=''):
        filename = self.create_temp_filename(suffix)
        yield filename
        os.remove(filename)

    def assertArrayEqual(self, a, b):
        return numpy.testing.assert_array_equal(a, b)

    def assertArrayAlmostEqual(self, a, b, *args, **kwargs):
        return numpy.testing.assert_array_almost_equal(a, b, *args, **kwargs)


class GraphicsTest(MontyTest):
    def tearDown(self):
        # If a plotting test bombs out it can leave the current figure in an
        # odd state, so we make sure it's been disposed of.
        plt.close()

    def _get_image_checksum(self, unique_id, resultant_checksum):
        checksum_result_path = get_result_path(('image_checksums', _PLATFORM, unique_id + '.txt'))
        if os.path.isfile(checksum_result_path):
            with open(checksum_result_path, 'r') as checksum_file:
                checksum = int(checksum_file.readline().strip())
        else:
            self._ensure_folder(checksum_result_path)
            logger.warning('Creating image checksum result file: %s', checksum_result_path)
            checksum = resultant_checksum
            open(checksum_result_path, 'w').writelines(str(checksum))
        return checksum

    def check_graphic(self):
        """
        Checks the CRC matches for the current matplotlib.pyplot figure, and
        closes the figure.
        
        """
        unique_id = self._unique_id()
        
        figure = plt.gcf()
        
        try:
            suffix = '.png'
            if _SAVE_FIGURES:
                file_path = os.path.join('image_results', unique_id) + suffix
                dir_path = os.path.dirname(file_path)
                if not os.path.isdir(dir_path):
                    os.makedirs(dir_path)
            else:
                file_path = self.create_temp_filename(suffix)

            figure.savefig(file_path)
            resultant_checksum = self.file_checksum(file_path)
            
            if not _SAVE_FIGURES:
                os.remove(file_path)

            checksum = self._get_image_checksum(unique_id, resultant_checksum)

            if _DISPLAY_FIGURES:
                if resultant_checksum != checksum:
                    print 'Test would have failed (new checksum: %s ; old checksum: %s)' % (resultant_checksum, checksum)
                plt.show()
            else:
                self.assertEqual(resultant_checksum, checksum, 'Image checksums not equal for %s' % unique_id)
        finally:
            plt.close()
