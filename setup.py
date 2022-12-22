#!/usr/bin/env python3

import glob
import os
from setuptools import setup

v = {}
v_path = os.path.join(*'src/_version.py'.split('/'))
with open(v_path) as v_file:
    exec(v_file.read(), v)

print(v)
print({v['__title__']: v['__title__']})
print([
        '%s=%s:main' % (os.path.splitext(os.path.basename(x))[0],
                        'src.'+os.path.splitext(os.path.basename(x))[0])
        for x in glob.iglob('src/[a-zA-Z]*py')
    ])
setup(
    name=v['__title__'],
    version=v['__version__'],
    packages=[v['__title__']],
    package_dir={v['__title__']: 'src'},
    entry_points={
        'console_scripts': [
            '%s=%s:main' % (
                os.path.splitext(os.path.basename(x))[0].replace('_', '-'),
                'src.'+os.path.splitext(os.path.basename(x))[0])
            for x in glob.iglob('src/[a-zA-Z]*py')
        ],
    },
    test_suite='tests',
    author=v['__author__'],
    author_email=v['__author_email__'],
    license=v['__license__'],
    url=v['__url__'],
    install_requires=[
        'numpy',
        'pandas',
        'pyyaml',
        'meteolib'
    ]
)
#    long_description=open('README.txt').read(),
