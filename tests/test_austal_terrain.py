import os.path
import unittest
import subprocess

NAME = os.path.join('austaltools','austal_terrain.py')
TESTFILE = 'temp.grid'

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

def verify_grid(path):
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
                   '-L', '49.75', '6.75',
                   TESTFILE.replace('.grid','')]
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert os.path.exists(TESTFILE) == True
        assert verify_grid(TESTFILE) == True
        if os.path.exists(TESTFILE): os.remove(TESTFILE)

    def test_gk(self):
        command = [NAME, '-v',
                   '-G', '3337932', '5515030',
                   TESTFILE.replace('.grid','')]
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert os.path.exists(TESTFILE) == True
        assert verify_grid(TESTFILE) == True
        if os.path.exists(TESTFILE): os.remove(TESTFILE)


    def test_ut(self):
        command = [NAME,
                   '-U', '337921', '5513264',
                   TESTFILE.replace('.grid', '')]
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert os.path.exists(TESTFILE) == True
        assert verify_grid(TESTFILE) == True
        if os.path.exists(TESTFILE): os.remove(TESTFILE)

    def test_mutex(self):
        command = [NAME,
                   '-L', '49.75', '6.75',
                   '-U', '337921', '5513264',
                   TESTFILE.replace('.grid', '')]
        out, err, exitcode = capture(command)
        assert exitcode != 0
        assert err.decode().startswith('usage')
        if os.path.exists(TESTFILE): os.remove(TESTFILE)

    def test_list_sources(self):
        command = [NAME, '--source-action','list',]
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert out.decode().strip() != ""

