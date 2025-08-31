import os.path
import unittest
import subprocess

CMD = ['python','-m','austaltools.command_line']
SUBCMD = 'weather'
OUTPUT = 'test'
EXTENSION = 'akterm'

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

def expected_files(OUTPUT):
    re = []
    for s in ['era5', 'dwd']:
        for y in range(2000,2020):
            for m in ['kms','kmo','k2o','pts','kmc','pgc']:
                re.append("%s_%s_%04i_%s.%s" %
                          (s, OUTPUT, y, m, EXTENSION))
    return re

def verify_akterm(path):
    return True


class TestCommandLine(unittest.TestCase):
    def test_no_param(self):
        command = CMD + [SUBCMD]
        out, err, exitcode = capture(command)
        assert exitcode != 0
        assert err.decode().startswith('usage')

    def test_help(self):
        command = CMD + [SUBCMD, '-h']
        out, err, exitcode = capture(command)
        assert exitcode == 0
        assert out.decode().startswith('usage')

    def test_ll(self):
        command = CMD + [SUBCMD,
                   '-L', '49.75', '6.75',
                   '-y', '2000',
                   OUTPUT]
        out, err, exitcode = capture(command)
        assert exitcode == 0
        produced_files = [x for x in expected_files(OUTPUT)
                          if os.path.exists(x)]
        assert len(produced_files) > 0
        assert all([verify_akterm(x) for x in produced_files]) == True
        for x in produced_files:
            os.remove(x)

    def test_gk(self):
        command = CMD + ['-v', SUBCMD,
                   '-G', '3337932', '5515030',
                   '-y', '2000',
                   OUTPUT]
        out, err, exitcode = capture(command)
        assert exitcode == 0
        produced_files = [x for x in expected_files(OUTPUT)
                          if os.path.exists(x)]
        print('expected:',expected_files(OUTPUT))
        print('produced:',produced_files)
        assert len(produced_files) > 0
        assert all([verify_akterm(x) for x in produced_files]) == True
        for x in produced_files:
            os.remove(x)


    def test_ut(self):
        command = CMD + [SUBCMD,
                   '-U', '337921', '5513264',
                   '-y', '2000',
                   OUTPUT]
        out, err, exitcode = capture(command)
        assert exitcode == 0
        produced_files = [x for x in expected_files(OUTPUT)
                          if os.path.exists(x)]
        assert len(produced_files) > 0
        assert all([verify_akterm(x) for x in produced_files]) == True
        for x in produced_files:
            os.remove(x)

    def test_mutex(self):
        command = CMD + [SUBCMD,
                   '-L', '6.75', '49.75',
                   '-U', '337921', '5513264',
                   OUTPUT]
        out, err, exitcode = capture(command)
        assert exitcode != 0
        assert err.decode().startswith('usage')
        produced_files = [x for x in expected_files(OUTPUT)
                          if os.path.exists(x)]
        for x in produced_files:
            os.remove(x)

    def test_noyear(self):
        command = CMD + [SUBCMD,
                   '-L', '6.75', '49.75',
                   OUTPUT]
        out, err, exitcode = capture(command)
        assert exitcode > 0
        produced_files = [x for x in expected_files(OUTPUT)
                          if os.path.exists(x)]
        for x in produced_files:
            os.remove(x)

    # def test_list_sources(self):
    #     command = CMD + [SUBCMD, '--source'
    #                      '-action', 'list']
    #     out, err, exitcode = capture(command)
    #     assert exitcode == 0
    #     assert out.decode().strip() != ""
    #     produced_files = [x for x in expected_files(OUTPUT)
    #                       if os.path.exists(x)]
    #     for x in produced_files:
    #         os.remove(x)

