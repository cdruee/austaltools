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


def make_zeitreihe():
    with open(os.path.join('tests','test.dmna'), 'r') as fi:
        with open(os.path.join('tests','zeitreihe.dmna'), 'w') as fo:
            fo.write(fi.read())


def make_cycle(name):
    lines = """
cycle01.so2:
    source: 01.so2
    start:
        at:
            time: 2-50/2
            unit: week
        offset:
            time: 12
            unit: hour
    list: [1.000, 1.000, 1.000, 2.000, 2.000, 2.000, 2.000, 2.000, 1.000, 1.000, 1.000]

"""
    with open(os.path.join('tests',name), 'w') as fo:
        fo.write(lines)


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

    def test_week5(self):
        make_zeitreihe()
        command = [NAME,
                   '-w', 'tests']
        out, err, exitcode = capture(command)
        assert exitcode == 1
        command = [NAME,
                   '-w', '-o', '1.0', 'tests']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        os.remove('tests/zeitreihe.dmna')

    def test_cycle(self):
        make_zeitreihe()
        make_cycle('cycle.yaml')
        capture(['cat','tests/cycle.yaml'])
        command = [NAME,
                   '-c', 'tests']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        os.renames('tests/cycle.yaml', 'tests/abcde.yaml')
        command = [NAME,
                   '-c', '-f', 'abcde.yaml', 'tests']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        os.remove('tests/zeitreihe.dmna')
        os.remove('tests/abcde.yaml')
