#!/usr/bin/env python3

import glob
import os
from setuptools import setup

v = {}
v_path = os.path.join(*'austaltools/_version.py'.split('/'))
with open(v_path) as v_file:
    exec(v_file.read(), v)

print(v)
print({v['__title__']: v['__title__']})
print([
        '%s=%s:main' % (
                os.path.splitext(os.path.basename(x))[0].replace('_', '-'),
                v['__title__'].replace('-', '_') + '.' +
                os.path.splitext(os.path.basename(x))[0])
        for x in glob.iglob(v['__title__'] + '/[a-zA-Z]*py')
    ])
setup(
    name=v['__title__'],
    version=v['__version__'],
    packages=[v['__title__']],
    package_dir={v['__title__']: v['__title__']},
    entry_points={
        'console_scripts': [
            '%s=%s:main' % (
                os.path.splitext(os.path.basename(x))[0].replace('_', '-'),
                v['__title__'].replace('-', '_') + '.' +
                os.path.splitext(os.path.basename(x))[0])
            for x in glob.iglob(v['__title__'] + '/[a-zA-Z]*py')
        ],
    },
    author=v['__author__'],
    author_email=v['__author_email__'],
    license=v['__license__'],
    url=v['__url__'],
    install_requires=[
        'numpy',
        'pandas',
        'pyyaml',
        'meteolib',
        'readmet',
        'matplotlib',
        'netCDF4'
    ],
    description=v['__description__'],
    long_description=open('README.md').read(),
    long_description_content_type='text/markdown',
)
