#!/usr/bin/env python
try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup


requirements = [ 'pyte', 'docopt' ]
try:
    import asyncio
except ImportError:
    requirements.append('asyncio')

setup(
        name='libpymux',
        author='Jonathan Slenders',
        version='0.1',
        license='LICENSE.txt',
        url='https://github.com/jonathanslenders/libpymux',
        description='Python terminal multiplexer (Pure Python tmux clone)',
        long_description=open("README.rst").read(),
        packages=['libpymux'],
        install_requires=requirements,
)
