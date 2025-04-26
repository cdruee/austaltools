import unittest
from unittest.mock import patch, MagicMock

import austaltools._geo
import austaltools._tools
from austaltools import _tools

class TestEstimateElevation(unittest.TestCase):
    def test_estimate_elevation(self):
        pass

class TestExpandSequence(unittest.TestCase):

    def test_comma_separated_list(self):
        # Test simple comma-separated list
        self.assertEqual(_tools.expand_sequence("1,2,3,4,5"), [1, 2, 3, 4, 5])

    def test_range_with_step(self):
        # Test range with step
        self.assertEqual(_tools.expand_sequence("1-9/2"), [1, 3, 5, 7, 9])

    def test_single_value(self):
        # Test single value handling
        self.assertEqual(_tools.expand_sequence("1"), [1])

    def test_single_negative_value(self):
        # Test single value handling
        self.assertEqual(_tools.expand_sequence("-1"), [-1])

    def test_range_without_step(self):
        # Test range without specifying a step
        self.assertEqual(_tools.expand_sequence("1-3"), [1, 2, 3])

    def test_unsorted_comma_separated_list_raises(self):
        # Test that unsorted comma-separated list raises ValueError
        with self.assertRaises(ValueError):
            _tools.expand_sequence("3,2,1")

    def test_illegal_character_raises(self):
        # Test that illegal characters in the input raise ValueError
        with self.assertRaises(ValueError):
            _tools.expand_sequence("1,a,3")

    def test_mutually_exclusive_characters_raises(self):
        # Test that mixing comma and range in the input raises ValueError
        with self.assertRaises(ValueError):
            _tools.expand_sequence("1-3,4")

    def test_invalid_step_raises(self):
        # Test a case where the step is not an integer should raise ValueError
        with self.assertRaises(ValueError):
            _tools.expand_sequence("1-5/x")

    def test_no_range_but_step(self):
        # Test a string that includes a step but no range
        with self.assertRaises(ValueError):
            self.assertRaises(_tools.expand_sequence("5/3"))

    def test_negative_range(self):
        # Check if negative numbers are handled correctly
        self.assertEqual(_tools.expand_sequence("-3--1"), [-3, -2, -1])

class TestGk2Ll(unittest.TestCase):

    def test_gk2ll(self):
        # reference
        la, lo, z = (50.0, 9.0, 0.0)
        (lat, lon) = austaltools._geo.gk2ll(3500074.92, 5540407.23)
        # Assert
        self.assertAlmostEqual(lat, la, delta=0.0000001)
        self.assertAlmostEqual(lon, lo, delta=0.0000001)

class TestLl2Gk(unittest.TestCase):

    def test_ll2gk(self):
        # reference
        r, h, z = (3500074.92, 5540407.23, 0.)
        re, ho = austaltools._geo.ll2gk(50.0, 9.0)
        # Assert
        self.assertAlmostEqual(re, r, delta=0.01)
        self.assertAlmostEqual(ho, h, delta=0.01)

class TestUt2Ll(unittest.TestCase):

    def test_ut2ll(self):
        # reference
        la, lo, z = (50.0, 9.0, 0.0)
        (lat, lon) = austaltools._geo.ut2ll(500000, 5538630.70)
        # Assert
        self.assertAlmostEqual(lat, la, delta=0.0000001)
        self.assertAlmostEqual(lon, lo, delta=0.0000001)

class TestLl2Ut(unittest.TestCase):

    def test_ll2ut(self):
        # reference
        r, h, z = (500000, 5538630.70, 0.)
        re, ho  = austaltools._geo.ll2ut(50.0, 9.0)
        # Assert
        self.assertAlmostEqual(re, r, delta=0.01)
        self.assertAlmostEqual(ho, h, delta=0.01)

class TestSphericDistance(unittest.TestCase):

    def test_spheric_distance(self):
        distance = austaltools._geo.spheric_distance(0, 0, 0, 1)
        self.assertAlmostEqual(distance, 111.19, places=2)

class FindAustxt(unittest.TestCase):
    def test_find_austxt(self):
        pass

class GetAustxt(unittest.TestCase):
    def test_get_austxt(self):
        pass

class PutAustxt(unittest.TestCase):
    def test_put_austxt(self):
        pass

class TestSlugify(unittest.TestCase):

    def test_slugify(self):
        self.assertEqual(_tools.slugify("Simple text"),
                         "simple-text")
        self.assertEqual(_tools.slugify("café", allow_unicode=True),
                         "café")
        self.assertEqual(_tools.slugify("café"),
                         "cafe")

class TestXmlpath(unittest.TestCase):

    def test_xmlpath(self):
        xml_string = '<root><element>Text</element></root>'
        result = _tools.xmlpath(xml_string, 'element')
        self.assertEqual(result, ['Text'])

class TestJsonpath(unittest.TestCase):

    def test_jsonpath(self):
        json_obj = {'items': [{'id': 1, 'name': 'Item 1'},
                              {'id': 2, 'name': 'Item 2', 'extra': 'yes'}]}
        result = _tools.jsonpath(json_obj, 'items/name')
        self.assertEqual(result, ['Item 1', 'Item 2'])

class TestWindLibrary(unittest.TestCase):

    def test_wind_library(self):
        path = '/some/path/lib'
        self.assertEqual(_tools.wind_library(path), path)

class TestAnalyzeName(unittest.TestCase):

    def test_analyze_name(self):
        with self.assertRaises(ValueError):
            _tools.analyze_name("w00")

        self.assertEqual(
            _tools.analyze_name("w6035a41.dmna"),
            (4, 35, 6)
        )

        self.assertEqual(
            _tools.analyze_name("w30sna00.dmna"),
            (0, 18, 3)
        )


class TestWindFiles(unittest.TestCase):
    files = ['w1018a00.dmna', 'w1027a00.dmnb', 'w2027a00.dmna',
             'w3018a00.dmnb', 'w4018a00.dmna', 'w4027a00.dmnb',
             'w5027a00.dmna', 'w6018a00.dmnb', 'zg00.dmna',
             'w1018a00.dmnb', 'w2018a00.dmna', 'w2027a00.dmnb',
             'w3027a00.dmna', 'w4018a00.dmnb', 'w5018a00.dmna',
             'w5027a00.dmnb', 'w6027a00.dmna', 'zp00.dmna',
             'w1027a00.dmna', 'w2018a00.dmnb', 'w3018a00.dmna',
             'w3027a00.dmnb', 'w4027a00.dmna', 'w5018a00.dmnb',
             'w6018a00.dmna', 'w6027a00.dmnb']

    @patch('os.listdir', return_value=files)
    def test_wind_files(self, mock_listdir):
        result = _tools.wind_files('/some/path')
        self.assertIn('name', result)
        self.assertTrue(all([x in self.files for x in result['name']]))
        self.assertTrue(all([x in result['name'] for x in self.files
                            if x.startswith('w') and x.endswith('a')]))
        self.assertTrue(all([x in [18,27] for x in result['wdir']]))
        self.assertTrue(all([int(x[6:7]) == y
                         for x,y in zip(result['name'],result['grid'])]))
        self.assertTrue(all([int(x[1:2]) == y
                         for x,y in zip(result['name'],result['stab'])]))


class TestReadWind(unittest.TestCase):

    def test_read_wind(self):
        pass

class TestReadZ0(unittest.TestCase):

    def test_read_z0(self):
        pass


class TestStr2Bool(unittest.TestCase):

    def test_true_cases(self):
        # Test cases that should return True
        true_inputs = ['yes', 'Yes', 'YES', 'true', 'True', 'TRUE',
                       'y', 'Y', 't', 'T', '1', True]
        for inp in true_inputs:
            self.assertTrue(_tools.str2bool(inp))

    def test_false_cases(self):
        # Test cases that should return False
        false_inputs = ['no', 'No', 'NO', 'false', 'False', 'FALSE',
                        'n', 'N', 'f', 'F', '0', False]
        for inp in false_inputs:
            self.assertFalse(_tools.str2bool(inp))

    def test_invalid_cases(self):
        # Test cases that should raise a ValueError
        invalid_inputs = ['maybe', 'random', '', 'yesno', '123']
        for inp in invalid_inputs:
            with self.assertRaises(ValueError):
                _tools.str2bool(inp)

    def test_passthrough_bool(self):
        # Test that boolean inputs pass through
        self.assertTrue(_tools.str2bool(True))
        self.assertFalse(_tools.str2bool(False))