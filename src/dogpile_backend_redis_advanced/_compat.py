from six import PY3
from six.moves import cPickle as pickle

if PY3:

    def u(s):
        return s


else:

    def u(s):
        return unicode(s, "utf-8")  # noqa
