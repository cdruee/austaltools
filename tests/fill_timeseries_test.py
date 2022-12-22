import os

import unittest
import subprocess

def capture(command):
    proc = subprocess.Popen(command,
        stdout = subprocess.PIPE,
        stderr = subprocess.PIPE,
    )
    out,err = proc.communicate()
    return out, err, proc.returncode

class Test_fill_timeseries_cli(unittest.TestCase):
    def test_no_param(self):
        command = ['python','src/austal_fill_timeseries.py']
        out, err, exitcode = capture(command)
        assert exitcode == 2

    def test_help(self):
        command = ['python','src/austal_fill_timeseries.py','-h']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert out.decode().startswith('usage')

    def test_rewrite(self):
        with open('tests/test.dmna','r') as fi:
            with open('tests/zeitreihe.dmna', 'w') as fo:
              fo.write(fi.read())
        command = ['python','src/austal_fill_timeseries.py','-c','tests']
        out, err, exitcode = capture(command)
        # assert exitcode == 0
        assert err == b''
        capture(['diff','-w','tests/zeitreihe.dmna','tests/test.dmna'])