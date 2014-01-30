from .invalidate import Redraw
from .layout import Location
from .log import logger
from .statusbar import StatusBar
from .window import Window

from collections import defaultdict
from pyte.screens import Char

import asyncio
import weakref

loop = asyncio.get_event_loop()


MAX_WORKERS = 1024 # Max number of threads for the pane runners.


class Session:
    """
    A session is a container of windows (which at their turn contain panes) and
    is responsible for window management.
    """
    def __init__(self):
        self.renderers = []
        self.windows = [ ]
        self.active_window = None

        self._last_char_buffers = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: Char)))

        self._invalidated = False
        self._invalidate_parts = 0

        self.status_bar = StatusBar(weakref.ref(self))

        self.invalidate()

    def invalidate(self, invalidate_parts=Redraw.All):
        """ Schedule repaint. """
        self._invalidate_parts |= invalidate_parts

        if not self._invalidated:
            logger.info('Scheduling repaint: %r' % self._invalidate_parts)
            self._invalidated = True
            loop.call_soon(lambda: asyncio.async(self.repaint()))

    def repaint(self):
        parts = self._invalidate_parts

        if not self.active_window:
            char_diffs = { }
        else:
            # Dump diffs for visible panes
            def get_previous_dump(pane):
                if self._invalidate_parts & Redraw.ClearFirst:
                    return None
                else:
                    return self._last_char_buffers[pane]

            char_diffs = {
                pane:pane.screen.dump_character_diff(get_previous_dump(pane))
                for pane in self.active_window.panes }

        self._invalidate_parts = 0

        for r in self.renderers:
            yield from r.repaint(parts, char_diffs)

        # Apply diffs
        for pane, diff in char_diffs.items():
            for y, line_data in diff.items():
                for x, char in line_data.items():
                    self._last_char_buffers[pane][y][x] = char

        # Reschedule again, if something changed while rendering in the
        # meantime.
        self._invalidated = False
        if self._invalidate_parts:
            self.invalidate(self._invalidate_parts)

    def add_renderer(self, renderer):
        """ Add this session renderer. """
        renderer.session = weakref.ref(self)

        self.renderers.append(renderer)
        self.update_size()

    def remove_renderer(self, renderer):
        renderer.session = None
        self.renderers.remove(renderer)
        self.update_size()

    @property
    def active_pane(self):
        """
        The active pane: the pane that is focussed in the active window.
        """
        if self.active_window:
            return self.active_window.active_pane
        else:
            return None

    def add_window(self, window):
        """
        Add new window.
        """
        self.active_window = window
        self.windows.append(window)
        window.session = weakref.ref(self)

        self.update_size()
        self.invalidate(Redraw.All)
        return window

    def update_size(self):
        """
        Take the sizes of all the renderers, and scale the layout according to
        the smallest client.
        """
        sizes = [ r.get_size() for r in self.renderers ]
        if sizes:
            self.sx = min(s.x for s in sizes)
            self.sy = min(s.y for s in sizes)
        else:
            self.sx = 80
            self.sy = 40

        # Honor minimal size. TODO: show "Too small" in that case.
        if self.sx < 10:
            self.sx = 10
        if self.sy < 3:
            self.sy = 3

        for window in self.windows:
            # Resize windows. (keep one line for the status bar.)
            window.layout.set_location(Location(0, 0, self.sx, self.sy - 1))

        self.invalidate(Redraw.All)

    # Commands

    def send_input_to_current_pane(self, data):
        if self.active_pane:
            logger.info('Sending %r' % b''.join(data))
            self.active_pane.write_input(b''.join(data))

    def focus_next_window(self):
        if self.active_window and self.windows:
            try:
                index = self.windows.index(self.active_window) + 1
            except ValueError:
                index = 0
            self.active_window = self.windows[index % len(self.windows)]
            self.invalidate(Redraw.All)

    def kill_current_pane(self):
        if self.active_pane:
            self.active_pane.kill_process()

    def resize_current_tile(self, direction='R', amount=1):
        self.active_pane.parent.resize_tile(direction, amount)
        self.invalidate(Redraw.All)

    def move_focus(self, direction='R'):
        self.active_window.move_focus(direction)
        self.invalidate(Redraw.Cursor | Redraw.Borders)

