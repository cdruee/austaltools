import unittest
import os
import subprocess

CMD = ['python','-m','austaltools.command_line']
COMMAND = 'fill-timeseries'


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
        command = CMD + [COMMAND]
        out, err, exitcode = capture(command)
        assert exitcode == 2

    def test_help(self):
        # test help pop up on blank command
        command = CMD + [COMMAND]
        out, err, exitcode = capture(command)
        assert exitcode == 2
        assert err.decode().startswith('usage')
        # test help wanted
        command = CMD + [COMMAND,
                   '-h']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert out.decode().startswith('usage')

    def test_week5(self):
        make_zeitreihe()
        # other directory, missing options
        command = CMD + ['-d', 'tests', COMMAND]
        out, err, exitcode = capture(command)
        assert exitcode == 2
        # other directory, output only
        command = CMD + ['-d', 'tests', COMMAND,
                   '-w', '-o', '1.0']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        os.remove('tests/zeitreihe.dmna')

    def test_cycle(self):
        make_zeitreihe()
        make_cycle('cycle.yaml')
        capture(['cat','tests/cycle.yaml'])
        # cycle file, implicit default name
        command = CMD + ['-d', 'tests', COMMAND,
                   '-c']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        # cycle file, do not accept filename after -c
        command = CMD + ['-d', 'tests', COMMAND,
                   '-c', 'cycle.yaml']
        out, err, exitcode = capture(command)
        assert exitcode == 2
        # cycle file, explicit default name
        command = CMD + ['-d', 'tests', COMMAND,
                   '-c', '-f', 'cycle.yaml']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        os.renames('tests/cycle.yaml', 'tests/abcde.yaml')
        # cycle file, non-default name
        command = CMD + ['-d', 'tests', COMMAND,
                   '-c', '-f', 'abcde.yaml']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        os.remove('tests/zeitreihe.dmna')
        os.remove('tests/abcde.yaml')
