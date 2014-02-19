#!/usr/bin/env python
"""
Usage:
    multitail.py <filename> <filename>...

Options:
  -h --help     : Display this help text

Splits the terminal in several panes, each running "tail -f". Press Ctrl-C in a
pane to terminal. Make sure that all the files to be monitored exist.
"""
from asyncio.protocols import BaseProtocol
from libpymux.input import InputProtocol
from libpymux.panes import ExecPane
from libpymux.renderer import PipeRenderer
from libpymux.session import Session
from libpymux.std import raw_mode
from libpymux.utils import alternate_screen, call_on_sigwinch
from libpymux.window import Window

import os, sys
import weakref
import asyncio
import docopt


class OurInputProtocol(InputProtocol):
    def get_bindings(self):
        return { }


class TailPane(ExecPane):
    def __init__(self, filename):
        self.filename = filename
        super().__init__()

    def _exec(self):
        os.execv('/usr/bin/tail', ['tail', '-f', self.filename])


@asyncio.coroutine
def run(filenames):
    # Output transport/protocol
    output_transport, output_protocol = yield from loop.connect_write_pipe(BaseProtocol, os.fdopen(0, 'wb'))

    with raw_mode(sys.stdin.fileno()):
        # Enter alternate screen buffer
        with alternate_screen(output_transport.write):
            # Create session and renderer
            session = Session()
            renderer = PipeRenderer(output_transport.write)
            session.add_renderer(renderer)

            # Setup layout
            window = Window()
            session.add_window(window)
            panes = []

            for filename in filenames:
                pane = TailPane(filename)
                window.add_pane(pane, vsplit=False)
                panes.append(pane)

            # handle resize events
            call_on_sigwinch(session.update_size)

            # Input transport/protocol
            input_transport, input_protocol = yield from loop.connect_read_pipe(
                                lambda:OurInputProtocol(session), sys.stdin)

            @asyncio.coroutine
            def run_pane(p):
                yield from p.run()
                window.remove_pane(p)

            # Wait for everything to finish
            yield from asyncio.gather(* [ asyncio.async(run_pane(p)) for p in panes ])


if __name__ == '__main__':
    a = docopt.docopt(__doc__)
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run(a['<filename>']))
