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
    def get_bindings(self):
        return {
            b'\x01': lambda: self.send_input_to_current_pane(b'\x01'),
            b'H': lambda: self.session.move_focus('L'),
            b'L': lambda: self.session.move_focus('R'),
        }

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
            renderer = PipeRenderer(output_transport.write)
            session.add_renderer(renderer)

            # Setup layout
            window = Window()
            session.add_window(window)
            pane1 = BashPane()
            pane2 = BashPane()
            window.add_pane(pane1)
            window.add_pane(pane2, vsplit=True)

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
            yield from asyncio.gather(
                    asyncio.async(run_pane(pane1)),
                    asyncio.async(run_pane(pane2))) # XXX: if we call pane1.run() twice. We get very weird errors!!!


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(run())
