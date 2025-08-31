import logging
import os
import subprocess
import unittest

import numpy as np

import austaltools.import_buildings as prog
import austaltools._tools as _tools

CMD = ['python','-m','austaltools.command_line']
SUBCMD = "import-buildings"

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

def capture(command):
    proc = subprocess.Popen(command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            )
    out, err = proc.communicate()
    print('command: %s' % command )
    print('command stdout: \n' + out.decode())
    print('command stderr: \n' + err.decode())
    print('cmd exit code : \n%s' % proc.returncode)
    return out, err, proc.returncode

def rotate(point, center, angle):
    px, py = point
    cx, cy = center
    rad = np.deg2rad(angle)
    rx = cx + np.cos(rad) * (px - cx) - np.sin(rad) * (py - cy)
    ry = cy + np.sin(rad) * (px - cx) + np.cos(rad) * (py - cy)
    return (rx, ry)

def rot_corn(corners, angle):
    return [rotate(x, corners[0], angle)
               for x in corners]

def rot_bldg(build, angle):
    b = build
    b.w = b.w + angle
    return b

class TestCommandLine(unittest.TestCase):
    def test_no_param(self):
        command = CMD + [SUBCMD]
        out, err, exitcode = capture(command)
        assert exitcode == 1
        self.assertRegex(err.decode(), "not found")

    def test_help(self):
        command = CMD + [SUBCMD, '-h']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        self.assertRegex(out.decode(), "^usage")

class TestCheckTolerances(unittest.TestCase):
    org_corners = [(100, 0), (200, 0), (200, 150), (100, 150)]
    org_build = _tools.Building(x=100, y=0, a=100, b=150, w=0)
    def test_check_tolerances_0(self):
        self.assertTrue(prog.check_tolerances(
            prog.DEFT_TOLRANCE, self.org_build, self.org_corners))

    def test_check_tolerances_stillok(self):
        corners = []
        for i,p in enumerate(self.org_corners):
            corners.append(
                (p[0] + 0.9 * prog.DEFT_TOLRANCE * np.sin(i),
                 p[1] + 0.9 * prog.DEFT_TOLRANCE * np.cos(i))
            )
        self.assertTrue(prog.check_tolerances(
            prog.DEFT_TOLRANCE, self.org_build, corners))

    def test_check_tolerances_notok(self):
        corners = []
        for i,p in enumerate(self.org_corners):
            corners.append(
                (p[0] + 1.1 * prog.DEFT_TOLRANCE * np.sin(i),
                 p[1] + 1.1 * prog.DEFT_TOLRANCE * np.cos(i))
            )
        self.assertFalse(prog.check_tolerances(
            prog.DEFT_TOLRANCE, self.org_build, corners))

    def test_check_tolerances_otherok(self):
        corners = []
        for i,p in enumerate(self.org_corners):
            corners.append(
                (p[0] + 1.1 * prog.DEFT_TOLRANCE * np.sin(i),
                 p[1] + 1.1 * prog.DEFT_TOLRANCE * np.cos(i))
            )
        self.assertTrue(prog.check_tolerances(
            1.2 * prog.DEFT_TOLRANCE, self.org_build, corners))

    def test_check_tolerances_otherok(self):
        corners = []
        for i,p in enumerate(self.org_corners):
            corners.append(
                (p[0] + 1.1 * prog.DEFT_TOLRANCE * np.sin(i),
                 p[1] + 1.1 * prog.DEFT_TOLRANCE * np.cos(i))
            )
        self.assertTrue(prog.check_tolerances(
            1.2 * prog.DEFT_TOLRANCE, self.org_build, corners))

class TestRectangleFinding(unittest.TestCase):
    org_corners = [(100, 0), (200, 0), (200, 150), (100, 150)]
    org_build = _tools.Building(x=100, y=0, a=100, b=150, w=0)

    def check_rotate(self, angle):
        rot_corners = rot_corn(self.org_corners, angle)
        rot_build = rot_bldg(self.org_build, angle)
        build = prog.find_building_around(rot_corners,
                                          prog.DEFT_TOLRANCE)
        print(format(self.org_corners) + '\n' +
              format(rot_corners)+ '\n' +
              format(rot_build) + '\n' +
              format(prog.building_corners(rot_build)) + '\n' +
              format(build) + '\n' +
              format(prog.building_corners(build))
              )
        return prog.check_tolerances(
            prog.DEFT_TOLRANCE,
            prog.find_building_around(rot_corners,
                                      prog.DEFT_TOLRANCE),
            rot_corners)
    def test_check_rotate_0_1(self):
        self.assertTrue(self.check_rotate(0.1))

    def test_check_rotate_1(self):
        self.assertTrue(self.check_rotate(1))

    def test_check_rotate_45(self):
        self.assertTrue(self.check_rotate(45))

    def test_check_rotate_89(self):
        self.assertTrue(self.check_rotate(89))

    def test_check_rotate_90(self):
        self.assertTrue(self.check_rotate(90))

    def test_check_rotate_m89(self):
        self.assertTrue(self.check_rotate(-89))

    def test_check_rotate_m170(self):
        self.assertTrue(self.check_rotate(-170))


class TestBadPoints(unittest.TestCase):
    org_corners = [(100, 0), (200, 0), (200, 150), (100, 150), (100, 0), (0,50)]
    rot_corners = rot_corn(org_corners, 20)

    def check_num_points(self, num):
        bdg = prog.find_building_around(self.rot_corners[0:num],
                                        prog.DEFT_TOLRANCE)
        if bdg is None:
            res = False
        else:
            res = prog.check_tolerances(
            prog.DEFT_TOLRANCE, bdg, self.rot_corners[0:4])
        return res
    def test_2_points(self):
        with self.assertRaises(ValueError):
            self.check_num_points(2)
    def test_3_points(self):
        self.assertTrue(self.check_num_points(3))
    def test_4_points(self):
        self.assertTrue(self.check_num_points(4))
    def test_5_points(self):
        self.assertTrue(self.check_num_points(5))
    def test_irreg_points(self):
        self.assertFalse(self.check_num_points(6))
