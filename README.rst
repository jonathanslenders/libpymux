libpymux
========

Library for terminal multiplexing in Python.
This is the library that's used by pymux, a pure Python tmux clone.

Dependencies
------------

- asyncio: It requires the asyncio library for event handling. This means it
  will also require Python 3.3, but Python 3.4 is recommended. (At least the Hg
  version of 10/01/2014 required.)
- pyte: A python library for handling vt100 escape codes.
