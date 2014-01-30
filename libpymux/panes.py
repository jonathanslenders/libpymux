
import asyncio
import resource
import pyte
import os
import io
import signal

from .log import logger
from .utils import set_size
from .pexpect_utils import pty_make_controlling_tty
from .layout import Container, Location
from .screen import BetterScreen
from .invalidate import Redraw

loop = asyncio.get_event_loop()


class Position:
    # Bit flags
    Top = 1
    Bottom = 2
    Left = 4
    Right = 8


class CellPosition:
    """ Position of a cell according to a single pane. """
    Outside = 0
    Inside = 2048

    TopBorder = Position.Top
    RightBorder = Position.Right
    BottomBorder = Position.Bottom
    LeftBorder = Position.Left
    TopLeftBorder = Position.Top | Position.Left
    TopRightBorder = Position.Top | Position.Right
    BottomRightBorder = Position.Bottom | Position.Right
    BottomLeftBorder = Position.Bottom | Position.Left


class BorderType:
    """ Position of a cell in a window. """
    Outside = 0
    Inside = 2048

    # Cross join
    Join = Position.Left | Position.Top | Position.Bottom | Position.Right

    BottomJoin = Position.Left | Position.Right | Position.Top
    TopJoin = Position.Left | Position.Right | Position.Bottom
    LeftJoin = Position.Right | Position.Top | Position.Bottom
    RightJoin = Position.Left | Position.Top | Position.Bottom

    # In the middle of a border
    Horizontal = Position.Left | Position.Right
    Vertical = Position.Bottom | Position.Top

    BottomRight = Position.Left | Position.Top
    TopRight = Position.Left | Position.Bottom
    BottomLeft = Position.Right | Position.Top
    TopLeft = Position.Right | Position.Bottom


class SubProcessProtocol(asyncio.protocols.SubprocessProtocol):
    def __init__(self, write_output):
        self.transport = None
        self._write_output = write_output

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self._write_output(data.decode('utf-8'))




class Pane(Container):
    _counter = 0

    def __init__(self):
        super().__init__()

        self.window = None # Weakref set by window.add

        # Pane position.
        self.px = 0
        self.py = 0

        # Pane size
        self.sx = 120
        self.sy = 24

        self.location = Location(self.py, self.py, self.sx, self.sy)

        # Create output stream and attach to screen
        self.screen = BetterScreen(self.sx, self.sy)
        self.stream = pyte.Stream()
        self.stream.attach(self.screen)

        # Create pseudo terminal for this pane.
        self.master, self.slave = os.openpty()

        # Master side -> attached to terminal emulator.
        self.shell_out = io.open(self.master, 'rb', 0)

        # Slave side -> attached to process.
        set_size(self.slave, self.sy, self.sx)

        self.id = self._next_id()

    @classmethod
    def _next_id(cls):
        cls._counter += 1
        return cls._counter

    def invalidate(self):
        """
        Invalidate session when this pane is in the active window.
        """
        window = self.window()
        if window:
            session = window.session()
            if session.active_window == window:
                window.invalidate(Redraw.Panes)

    @property
    def panes(self):
        yield self

    def add(self, child):
        # Pane is a leaf node. Disallow
        raise Exception('Not allowed to add childnodes to a Pane node.')

    def set_location(self, location):
        """ Set position of pane in window. """
        logger.info('set_position(px=%r, py=%r, sx=%r, sy=%r)' %
                            (location.px, location.py, location.sx, location.sy))
        self.location = location

        self.px = location.px
        self.py = location.py
        self.sx = location.sx
        self.sy = location.sy
        self.screen.resize(self.sy, self.sx)
        set_size(self.slave, self.sy, self.sx)

        self.invalidate()


    def write_output(self, data):
        """ Write data received from the application into the pane and rerender. """
        self.stream.feed(data)
        self.invalidate()

    def write_input(self, data):
        """ Write user key strokes to the input. """
        os.write(self.master, data)

    @property
    def cursor_position(self):
        return self.screen.cursor.y, self.screen.cursor.x

    def _get_border_type(self, x, y):
        return {
            CellPosition.TopBorder: BorderType.Horizontal,
            CellPosition.BottomBorder: BorderType.Horizontal,
            CellPosition.LeftBorder: BorderType.Vertical,
            CellPosition.RightBorder: BorderType.Vertical,

            CellPosition.TopLeftBorder: BorderType.TopLeft,
            CellPosition.TopRightBorder: BorderType.TopRight,
            CellPosition.BottomLeftBorder: BorderType.BottomLeft,
            CellPosition.BottomRightBorder: BorderType.BottomRight,

            CellPosition.Inside: BorderType.Inside,
            CellPosition.Outside: BorderType.Outside,
        }[ self._get_cell_position(x,y) ]

    def is_inside(self, x, y):
        """ True when this coordinate appears inside this pane. """
        return (x >= self.px and x < self.px + self.sx and
                y >= self.py and y < self.py + self.sy)

    def _get_cell_position(self, x, y):
        """ For a given (x,y) cell, return the CellPosition. """
        # If outside this pane, skip it.
        if x < self.px - 1 or x > self.px + self.sx or y < self.py - 1 or y > self.py + self.sy:
            return CellPosition.Outside

#        #  If inside, return that.
#        if self.is_inside(x, y):
#            return CellPosition.Inside

        # Use bitmask for borders:
        mask = 0

        if y == self.py - 1:
            mask |= Position.Top

        if y == self.py + self.sy:
            mask |= Position.Bottom

        if x == self.px - 1:
            mask |= Position.Left

        if x == self.px + self.sx:
            mask |= Position.Right

        return mask

        if mask:
            return mask
        else:
            raise Exception("This can't happen")
            #return CellPosition.Inside


class ExecPane(Pane):
    def __init__(self, pane_executor=None):
        super().__init__()

        self.pane_executor = pane_executor
        self.finished = False
        self.process_id = None

    @asyncio.coroutine
    def run(self):
        try:
            # Connect read pipe to process
            read_transport, read_protocol = yield from loop.connect_read_pipe(
                                lambda:SubProcessProtocol(self.write_output), self.shell_out)

            # Run process in executor, wait for that to finish.
            yield from self._run_fork()

            # Set finished.
            self.finished = True # TODO: close pseudo terminal.
        except Exception as e:
            logger.error('CRASH: ' + repr(e))

    @asyncio.coroutine
    def _run_fork(self): # TODO: rename!
        """
        Fork this process. The child gets attached to the slave side of the
        pseudo terminal.
        """
        pid = os.fork()
        if pid == 0: # TODO: <0 is fail
            yield from self._in_child()

        elif pid > 0:
            yield from self._in_parent(pid)

    @asyncio.coroutine
    def _in_child(self):
        os.close(self.master)

        pty_make_controlling_tty(self.slave)

        # In the fork, set the stdin/out/err to our slave pty.
        os.dup2(self.slave, 0)
        os.dup2(self.slave, 1)
        os.dup2(self.slave, 2)

        # Set environment variables for child process
        os.environ['PYMUX_PANE'] = 'TODO:Pane value'

        # Execute in child.
        try:
            self._exec()
        except Exception as e:
            os._exit(1)
        os._exit(0)

    @asyncio.coroutine
    def _in_parent(self, pid):
        logger.info('Forked process: %r' % pid)
        self.process_id = pid

        # Call waitpid in parent. (waitpid is blocking -> use executor.)
        pid, status = yield from loop.run_in_executor(self.pane_executor, os.waitpid, pid, 0)
        logger.info('Process ended, status=%r' % status)

    def kill_process(self):
        """ Send SIGKILL to the process running in this pane. """
        if self.process_id:
            logger.info('Killing process %r' % self.process_id)
            os.kill(self.process_id, signal.SIGKILL)

    def _exec(self):
        """
        (To be called inside the fork)
        Run Python code and call exec.
        Run external process using "exec"
        """
        self._close_file_descriptors()
        self._do_exec()

    def _close_file_descriptors(self):
        # Do not allow child to inherit open file descriptors from parent.
        # (In case that we keep running Python code. We shouldn't close them.
        # because the garbage collector is still active, and he will close them
        # eventually.)
        max_fd = resource.getrlimit(resource.RLIMIT_NOFILE)[-1]
        for i in range(3, max_fd):
            if i != self.slave:
                try:
                    os.close(i)
                except OSError:
                    pass

    def _do_exec(self):
        raise NotImplementedError

