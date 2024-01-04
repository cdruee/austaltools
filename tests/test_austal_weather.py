import os.path
import unittest
import subprocess

NAME = os.path.join('austaltools','austal_weather.py')
TESTFILE = 'test.akterm'
EXTENSION = '.akterm'

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

def verify_akterm(path):
    return True

class TestCommandLine(unittest.TestCase):
    def test_no_param(self):
        command = [NAME]
        out, err, exitcode = capture(command)
        assert exitcode != 0
        assert out.decode().startswith('usage')

    def test_help(self):
        command = [NAME, '-h']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert out.decode().startswith('usage')

    def test_ll(self):
        command = [NAME,
                   '-L', '6.75', '49.75',
                   '-y', '2000',
                   TESTFILE.replace(EXTENSION,'')]
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert os.path.exists(TESTFILE) == True
        assert verify_akterm(TESTFILE) == True
        if os.path.exists(TESTFILE): os.remove(TESTFILE)

    def test_gk(self):
        command = [NAME, '-v',
                   '-G', '3337932', '5515030',
                   '-y', '2000',
                   TESTFILE.replace(EXTENSION,'')]
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert os.path.exists(TESTFILE) == True
        assert verify_akterm(TESTFILE) == True
        if os.path.exists(TESTFILE): os.remove(TESTFILE)


    def test_ut(self):
        command = [NAME,
                   '-U', '337921', '5513264',
                   '-y', '2000',
                   TESTFILE.replace(EXTENSION, '')]
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert os.path.exists(TESTFILE) == True
        assert verify_akterm(TESTFILE) == True
        if os.path.exists(TESTFILE): os.remove(TESTFILE)

    def test_mutex(self):
        command = [NAME,
                   '-L', '6.75', '49.75',
                   '-U', '337921', '5513264',
                   TESTFILE.replace(EXTENSION, '')]
        out, err, exitcode = capture(command)
        assert exitcode != 0
        assert err.decode().startswith('usage')
        if os.path.exists(TESTFILE): os.remove(TESTFILE)

    def test_noyear(self):
        command = [NAME,
                   '-L', '6.75', '49.75',
                   TESTFILE.replace(EXTENSION, '')]
        out, err, exitcode = capture(command)
        assert exitcode != 1
        if os.path.exists(TESTFILE): os.remove(TESTFILE)

    def test_list_sources(self):
        command = [NAME, '--sources-action', 'list']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert out.decode().strip() != ""

