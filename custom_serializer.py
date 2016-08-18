import datetime
import msgpack
import cPickle

# ==============================================================================


class MsgpackSerializer(object):
    """unified, self-contained serializer"""

    @classmethod
    def encode_datetime(cls, dt):
        """Serialize the given datetime.datetime object to a EPOCH seconds."""
        return {'__datetime__': True,
                '0': (dt - datetime.datetime(1970, 1, 1)).total_seconds()
                }

    @classmethod
    def encode_date(cls, d):
        """Serialize the given datetime.date object to a JSON string."""
        # Default is ISO 8601 compatible (standard notation).
        return {'__date__': True,
                '0': "%04d%02d%02d" % (d.year, d.month, d.day),
                }

    @classmethod
    def encode_timedelta(cls, t):
        """Serialize the given datetime.timedelta object to some seconds."""
        return {'__timedelta__': True,
                '0': t.total_seconds(),
                }

    @classmethod
    def decode_datedata(cls, obj):
        if b'__datetime__' in obj:
            obj = datetime.datetime.fromtimestamp(obj['0'])
        elif b'__date__' in obj:
            # is is MUCH faster to use date() than strptime
            # obj = datetime.datetime.strptime(obj['0'], "%Y%m%d").date()
            d = obj["0"]
            obj = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:8]))
        elif b'__timedelta__' in obj:
            obj = datetime.timedelta(seconds=obj['0'])
        return obj

    @classmethod
    def encoder(cls, o):
        if isinstance(o, datetime.datetime):
            return cls.encode_datetime(o)
        elif isinstance(o, datetime.date):
            return cls.encode_date(o)
        elif isinstance(o, datetime.timedelta):
            return cls.encode_timedelta(o)
        elif isinstance(o, set):
            return tuple(o)
        else:
            return o

    @classmethod
    def decoder(cls, obj):
        obj = cls.decode_datedata(obj)
        return obj

    @classmethod
    def dumps(cls, payload):
        v = msgpack.packb(payload, default=cls.encoder, use_bin_type=True)
        return v

    @classmethod
    def loads(cls, payload):
        v = msgpack.unpackb(payload, object_hook=cls.decoder, encoding="utf-8")
        return v


if __name__ == '__main__':
    
    import pprint
    import timeit
    
    sample_data = {'string': 'foo',
                   'int': 100,
                   'bool': True,
                   'list': [1, 2, 3, 4, 5, ],
                   'tuple': [1, 2, 3, 4, 5, ],
                   'dict': {'a': 1,
                            1: 'a',
                            },
                    'datetime': datetime.datetime.now(),
                    'date': datetime.date.today(),
                    'timedelta': datetime.timedelta(seconds=100),
                    }
    encoded_msgpack = MsgpackSerializer.dumps(sample_data)
    loaded_msgpack = MsgpackSerializer.loads(encoded_msgpack)
    
    print "==" * 40
    print "MSGPACK"
    print "- " * 40
    print "RAW"
    pprint.pprint(sample_data) 
    print "- " * 40
    print "ENCODED"
    pprint.pprint(encoded_msgpack) 
    print "- " * 40
    print "LOADED"
    pprint.pprint(loaded_msgpack)
    print "- " * 40
    

    encoded_pickle = cPickle.dumps(sample_data)
    loaded_pickle = cPickle.loads(encoded_pickle)

    iterations = 1000

    time_msgpack_dumps = timeit.timeit('MsgpackSerializer.dumps(sample_data)','from __main__ import MsgpackSerializer, sample_data', number=iterations)
    time_msgpack_loads = timeit.timeit('MsgpackSerializer.loads(encoded_msgpack)','from __main__ import MsgpackSerializer, encoded_msgpack', number=iterations)

    time_pickle_dumps = timeit.timeit('cPickle.dumps(sample_data)','from __main__ import cPickle, sample_data', number=iterations)
    time_pickle_loads = timeit.timeit('cPickle.loads(encoded_pickle)','from __main__ import cPickle, encoded_pickle', number=iterations)
    
    print "iterations = %s" % iterations
    print "MsgpackSerializer.dumps : %s" % time_msgpack_dumps
    print "MsgpackSerializer.loads : %s" % time_msgpack_loads
    print "cPickle.dumps           : %s" % time_pickle_dumps
    print "cPickle.loads           : %s" % time_pickle_loads
    
    
    
    
    
    