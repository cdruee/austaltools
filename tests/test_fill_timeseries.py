import unittest
import os
import subprocess

NAME = os.path.join('austaltools','austal_fill_timeseries.py')
def capture(command):
    proc = subprocess.Popen(command,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            )
    out, err = proc.communicate()
    print('command stdout: \n' + out.decode())
    print('command stderr: \n' + err.decode())
    print('cmd exit code : \n%s' % proc.returncode)
    return out, err, proc.returncode


class TestCommandLine(unittest.TestCase):
    def test_no_param(self):
        command = [NAME]
        out, err, exitcode = capture(command)
        assert exitcode == 2

    def test_help(self):
        command = [NAME,
                   '-h']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert out.decode().startswith('usage')

    def test_rewrite(self):
        with open('tests/test.dmna', 'r') as fi:
            with open('tests/zeitreihe.dmna', 'w') as fo:
                fo.write(fi.read())
        command = [NAME,
                   '-c', 'tests']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        out, err, exitcode = capture(['diff', '-w', 'tests/zeitreihe.dmna', 'tests/test.dmna'])
        assert exitcode == 0
        os.remove('tests/zeitreihe.dmna')
