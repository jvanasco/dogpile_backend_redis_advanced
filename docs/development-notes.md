To Do
--------------------------------------

I've been experimenting with handling the TTL within a hash bucket (instead of
using the **Redis** or **dogpile.cache** methods). This looks promising.  The
rationale is that it is easier for **Redis** to get/set an extra field from the
same hash, than it is to do separate calls to TTL/EXPIRES.

in code:

	- hset('example', 'foo', 'bar')
	- expires('example', 3600)
	+ hmset('example', {'foo': 'bar',
						'expires': time.time() + 3600,
						}

I've also been experimenting with blessing the result into a subclass of `dict`
that would do the object pair decoding lazily as-needed.
That would speed up most use cases.
