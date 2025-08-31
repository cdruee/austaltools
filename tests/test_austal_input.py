import logging
import os
import subprocess
import unittest

import sys
sys.path.insert(0,',,')

CMD = ['python','-m','austaltools.austal_input']
SUBCMD = "buildings-geojson"

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

class TestCommandLine(unittest.TestCase):
    def test_no_param(self):
        command = CMD + [SUBCMD]
        out, err, exitcode = capture(command)
        assert exitcode == 2
        self.assertRegex(err.decode(), "^usage")

    def test_help(self):
        command = CMD + [SUBCMD, '-h']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        self.assertRegex(out.decode(), "^usage")


class TestFuntionCall(unittest.TestCase):
    def test_no_param(self):
        from austaltools import austal_input
        with self.assertRaises(SystemExit) as cm:
            austal_input.main()
            self.assertEqual(cm.exception, "Error")

    def test_help(self):
        command = CMD + [SUBCMD, '-h']
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 0)
        self.assertRegex(out.decode(), "^usage")

