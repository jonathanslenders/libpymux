import array
import asyncio
import fcntl
import signal
import termios


def get_size(stdout):
    # Thanks to fabric (fabfile.org), and
    # http://sqizit.bartletts.id.au/2011/02/14/pseudo-terminals-in-python/
    """
    Get the size of this pseudo terminal.

    :returns: A (rows, cols) tuple.
    """
    #assert stdout.isatty()

    # Buffer for the C call
    buf = array.array('h', [0, 0, 0, 0 ])

    # Do TIOCGWINSZ (Get)
    #fcntl.ioctl(stdout.fileno(), termios.TIOCGWINSZ, buf, True)
    fcntl.ioctl(0, termios.TIOCGWINSZ, buf, True)

    # Return rows, cols
    return buf[0], buf[1]


def set_size(stdout_fileno, rows, cols):
    """
    Set terminal size.

    (This is also mainly for internal use. Setting the terminal size
    automatically happens when the window resizes. However, sometimes the process
    that created a pseudo terminal, and the process that's attached to the output window
    are not the same, e.g. in case of a telnet connection, or unix domain socket, and then
    we have to sync the sizes by hand.)
    """
    # Buffer for the C call
    buf = array.array('h', [rows, cols, 0, 0 ])

    # Do: TIOCSWINSZ (Set)
    fcntl.ioctl(stdout_fileno, termios.TIOCSWINSZ, buf)


def alternate_screen(write):
    class Context:
        def __enter__(self):
            # Enter alternate screen buffer
            write(b'\033[?1049h')

        def __exit__(self, *a):
            # Exit alternate screen buffer and make cursor visible again.
            write(b'\033[?1049l')
            write(b'\033[?25h')
    return Context()


def call_on_sigwinch(callback, loop=None):
    """
    Set a function to be called when the SIGWINCH signal is received.
    (Normally, on terminal resize.)
    """
    if loop is None:
        loop = asyncio.get_event_loop()

    def sigwinch_handler():
        loop.call_soon(callback)
    loop.add_signal_handler(signal.SIGWINCH, sigwinch_handler)
