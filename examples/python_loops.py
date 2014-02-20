#!/usr/bin/env python
"""
Usage:
    python_loops.py

Doesn't start any external processes. Just runs a Python while loop in the
panes.
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


class OurInputProtocol(InputProtocol):
    # Any key press will exit the application
    def __init__(self, session, done_callback):
        super().__init__(session)
        self._done = done_callback

    def data_received(self, data):
        self._done()


class PythonPane(ExecPane):
    @asyncio.coroutine
    def run_application(self):
        i = 0
        while True:
            i += 1
            self.write(b'hello ' + str(i).encode('utf-8') + b'\n')
            yield from asyncio.sleep(1)

        os.execv('/bin/bash', ['bash'])


@asyncio.coroutine
def run():
    finish_f = asyncio.Future()

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
            pane1 = PythonPane()
            pane2 = PythonPane()
            window.add_pane(pane1)
            window.add_pane(pane2, vsplit=True)

            # handle resize events
            call_on_sigwinch(session.update_size)

            # Input transport/protocol
            done = lambda: finish_f.set_result(None)
            yield from loop.connect_read_pipe(lambda:OurInputProtocol(session, done), sys.stdin)

            # Run panes
            asyncio.async(pane1.run())
            asyncio.async(pane2.run())

            # Wait for any key press to exit.
            yield from finish_f


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
