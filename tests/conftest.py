from _pytest.unittest import UnitTestCase
import sys
import logging

import logging.config

logging.config.fileConfig("log_tests.ini")


def is_unittest(obj):
    """Is obj a subclass of unittest.TestCase?

    Lifted from older versions of py.test, as this seems to be removed.

    """
    unittest = sys.modules.get("unittest")
    if unittest is None:
        return  # nobody can have derived unittest.TestCase
    try:
        return issubclass(obj, unittest.TestCase)
    except KeyboardInterrupt:
        raise
    except:
        return False


def pytest_pycollect_makeitem(collector, name, obj):
    if is_unittest(obj) and not obj.__name__.startswith("_"):
        # pytest changed in 5.4.0; things behave differently on py2 & py3
        return UnitTestCase.from_parent(collector, name=name)
        # pytest 4.6 is the last to support py2.7
        # https://docs.pytest.org/en/stable/py27-py34-deprecation.html
    else:
        return []
