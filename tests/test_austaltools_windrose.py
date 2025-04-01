import os.path
import unittest
import subprocess

NAME = os.path.join('austaltools','command_line.py')
SUBCMD = 'windrose'
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

scales = ['beaufort', '2ms', 'quantile', 'stability', 'halfyear', 'season']


class TestCommandLine(unittest.TestCase):
    def test_help(self):
        command = [NAME, SUBCMD, '-h']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert out.decode().startswith('usage')

    def test_no_param(self):
        command = [NAME, SUBCMD]
        out, err, exitcode = capture(command)
        self.assertEqual(exitcode, 1)
        self.assertRegex(err.decode(), 'austal.txt or austal2000.txt not found')

    def test_file_default(self):
        for sc in scales:
            command = [NAME, SUBCMD,
                       '-w', 'tests/example.akterm', '-p', '-s', sc]
            out, err, exitcode = capture(command)
            self.assertEqual(exitcode, 0)
            self.assertTrue(os.path.exists('windrose.png'))
            os.remove('windrose.png')

    def test_file_star(self):
        for sc in scales:
            command = [NAME, SUBCMD,
                       '-k', 'star',
                       '-w', 'tests/example.akterm',
                       '-p', '-s', sc]
            out, err, exitcode = capture(command)
            self.assertEqual(exitcode, 0)
            self.assertTrue(os.path.exists('windrose.png'))
            os.remove('windrose.png')
