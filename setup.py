import os
import re
import sys

from setuptools import setup, find_packages
from setuptools.command.test import test as TestCommand


class PyTest(TestCommand):
    user_options = [("pytest-args=", "a", "Arguments to pass to py.test")]

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


HERE = os.path.abspath(os.path.dirname(__file__))

v = open(os.path.join(HERE, "src", "dogpile_backend_redis_advanced", "__init__.py"))
VERSION = re.compile(r'.*__version__ = "(.*?)"', re.S).match(v.read()).group(1)
v.close()

long_description = description = "Advanced Redis plugins for `dogpile.cache`."
with open(os.path.join(HERE, "README.md")) as fp:
    long_description = fp.read()


install_requires = [
    "dogpile.cache>=1.0",
    "redis",
]

tests_require = install_requires + [
    "pytest",
    "pytest-cov",
    "mock",
    "msgpack-python",
]
testing_extras = [
    "flake8",
    "mypy",
    "tox",
]


setup(
    name="dogpile_backend_redis_advanced",
    version=VERSION,
    description=description,
    long_description=long_description,
    long_description_content_type="text/markdown",
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: BSD License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Programming Language :: Python :: 3.7",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    keywords="caching dogpile",
    author="Jonathan Vanasco",
    author_email="jonathan@findmeon.com",
    url="https://github.com/jvanasco/dogpile_backend_redis_advanced",
    license="BSD",
    packages=find_packages(
        where="src",
    ),
    package_dir={"": "src"},
    package_data={"dogpile_backend_redis_advanced": ["py.typed"]},
    include_package_data=True,
    zip_safe=False,
    install_requires=install_requires,
    tests_require=tests_require,
    extras_require={
        "testing": testing_extras,
    },
    cmdclass={"test": PyTest},
)
