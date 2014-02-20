#!/usr/bin/env python
"""
Usage:
    rot13_bash.py

Apply rot13 transformation on any application running inside this pane.
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
import codecs


class Rot13Renderer(PipeRenderer):
    def __init__(self, write_func):
        super().__init__(write_func)

    def _repaint_pane(self, pane, char_buffer):
        modified_char_buffer = { }

        # Do rot13
        for line_index, line_data in char_buffer.items():
            modified_char_buffer[line_index] = {}

            for column_index, char in line_data.items():
                data2 = codecs.encode(char.data, 'rot_13')
                modified_char_buffer[line_index][column_index] = char._replace(data=data2)

        return super()._repaint_pane(pane, modified_char_buffer)


class BashPane(ExecPane):
    def _exec(self):
        os.execv('/bin/bash', ['bash'])


@asyncio.coroutine
def run():
    # Output transport/protocol
    output_transport, output_protocol = yield from loop.connect_write_pipe(BaseProtocol, os.fdopen(0, 'wb'))

    with raw_mode(sys.stdin.fileno()):
        # Enter alternate screen buffer
        with alternate_screen(output_transport.write):
            # Create session and renderer
            session = Session()
            renderer = Rot13Renderer(output_transport.write)
            session.add_renderer(renderer)

            # Setup layout
            window = Window()
            session.add_window(window)
            pane = BashPane()
            window.add_pane(pane)

            # handle resize events
            call_on_sigwinch(session.update_size)

            # Input transport/protocol
            input_transport, input_protocol = yield from loop.connect_read_pipe(
                                lambda:InputProtocol(session), sys.stdin)

            # Wait for everything to finish
            yield from pane.run()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
