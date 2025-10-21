import os
import re

from setuptools import find_packages
from setuptools import setup

HERE = os.path.abspath(os.path.dirname(__file__))

v = open(os.path.join(HERE, "src", "dogpile_backend_redis_advanced", "__init__.py"))
VERSION = re.compile(r'.*__version__ = "(.*?)"', re.S).match(v.read()).group(1)
v.close()

long_description = description = "Advanced Redis plugins for `dogpile.cache`."
with open(os.path.join(HERE, "README.md")) as fp:
    long_description = fp.read()


install_requires = [
    "dogpile.cache>=1.5.0",
    "redis",
]

testing_extras = install_requires + [
    "flake8",
    "mypy",
    "pytest",
    "pytest-cov",
    "mock",
    "msgpack>=1.1.2",
    "msgpack-types",
    "tox",
    "types-mock",
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
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
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
    python_requires=">=3.10",  # dogpile.cache 1.5.0 requires 3.10
    include_package_data=True,
    zip_safe=False,
    install_requires=install_requires,
    extras_require={
        "testing": testing_extras,
    },
)
