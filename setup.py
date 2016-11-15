import os
import re
import sys

from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand


class PyTest(TestCommand):
    user_options = [('pytest-args=', 'a', "Arguments to pass to py.test")]

    def initialize_options(self):
        TestCommand.initialize_options(self)
        self.pytest_args = []

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        # import here, cause outside the eggs aren't loaded
        import pytest
        errno = pytest.main(self.pytest_args)
        sys.exit(errno)


v = open(
    os.path.join(
        os.path.dirname(__file__),
        'dogpile_backend_redis_advanced', '__init__.py')
)
VERSION = re.compile(r".*__version__ = '(.*?)'", re.S).match(v.read()).group(1)
v.close()

readme = os.path.join(os.path.dirname(__file__), 'README.md')
long_description = "Advanced redis plugins for dogpile.cache"
try:
    open(readme).read()
except:
    pass

setup(
    name='dogpile_backend_redis_advanced',
    version=VERSION,
    description="Advanced redis plugins for dogpile.cache.",
    long_description=long_description,
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
    keywords='caching dogpile',
    author='Jonathan Vanasco',
    author_email='jonathan@findmeon.com',
    url='https://github.com/jvanasco/dogpile_backend_redis_advanced',
    license='BSD',
    packages=find_packages('.', exclude=['tests*']),
    zip_safe=False,
    install_requires=['redis', 'dogpile.cache', ],
    tests_require=['pytest', 'pytest-cov', 'mock', 'msgpack-python', 'dogpile.cache', 'redis', ],
    cmdclass={'test': PyTest},
)
