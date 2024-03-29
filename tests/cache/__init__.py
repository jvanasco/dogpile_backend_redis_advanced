from functools import wraps
import pytest
import configparser
import io
import re
import sys
import time


# this was previously in dogpile.util.compat
win32 = sys.platform.startswith("win")

# end dogpile.util.compat


def eq_(a, b, msg=None):
    """Assert a == b, with repr messaging on failure."""
    assert a == b, msg or "%r != %r" % (a, b)


def is_(a, b, msg=None):
    """Assert a is b, with repr messaging on failure."""
    assert a is b, msg or "%r is not %r" % (a, b)


def ne_(a, b, msg=None):
    """Assert a != b, with repr messaging on failure."""
    assert a != b, msg or "%r == %r" % (a, b)


def assert_raises_message(except_cls, msg, callable_, *args, **kwargs):
    try:
        callable_(*args, **kwargs)
        assert False, "Callable did not raise an exception"
    except except_cls as e:
        assert re.search(msg, str(e)), "%r !~ %s" % (msg, e)


def winsleep():
    # sleep a for an amount of time
    # sufficient for windows time.time()
    # to change
    if win32:
        time.sleep(0.001)
