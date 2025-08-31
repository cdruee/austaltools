import os.path
import unittest
import subprocess

CMD = ['python','-m','austaltools.command_line']
SUBCMD = 'eap'
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
        command = CMD + [SUBCMD]
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 1)
        self.assertRegex(err.decode(), 'grid 0 not available')

    def test_help(self):
        command = CMD + [SUBCMD, '-h']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert out.decode().startswith('usage')

