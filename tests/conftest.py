from _pytest.unittest import UnitTestCase
import sys
import logging

import logging.config

logging.config.fileConfig("log_tests.ini")


import six


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


# pytest changed in 5.4.0; so things behave differently on py2 & py3
# because of how tests are collected, this might work...
if six.PY3:

    def pytest_pycollect_makeitem(collector, name, obj):
        if is_unittest(obj) and not obj.__name__.startswith("_"):
            return UnitTestCase.from_parent(collector, name=name)
        else:
            return []


else:

    def pytest_pycollect_makeitem(collector, name, obj):
        if is_unittest(obj) and not obj.__name__.startswith("_"):
            return UnitTestCase(name, parent=collector)
        else:
            return []
