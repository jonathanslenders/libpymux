import termios
import tty


class raw_mode(object):
    """
    with raw_mode(stdin):
        ''' the pseudo-terminal stdin is now used in raw mode '''
    """
    def __init__(self, fileno):
        self.fileno = fileno
        self.attrs_before = termios.tcgetattr(fileno)

    def __enter__(self):
        # NOTE: On os X systems, using pty.setraw() fails. Therefor we are using this:
        newattr = termios.tcgetattr(self.fileno)
        newattr[tty.LFLAG] = newattr[tty.LFLAG] & ~(
                        termios.ECHO | termios.ICANON | termios.IEXTEN | termios.ISIG)
        termios.tcsetattr(self.fileno, termios.TCSANOW, newattr)

    def __exit__(self, *a, **kw):
        termios.tcsetattr(self.fileno, termios.TCSANOW, self.attrs_before)

