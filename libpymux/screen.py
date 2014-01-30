"""
Custom `Screen` class for the `pyte` library.

Changes compared to the original `Screen` class:
    - We store the layout in a dict instead of a list, in order to have a
      scalable window. When the window size is reduced and increased again, the
      hidden text will appear again.
    - 256 colour support (xterm)
    - Per character diffs instead of per line diffs.
"""
from collections import defaultdict
from pyte import charsets as cs
from pyte import modes as mo
from pyte.graphics import FG, BG
from pyte.screens import Margins, Cursor, Char
import pyte

from .log import logger


# Patch pyte.graphics to accept High intensity colours as well.

FG.update({
    90: "hi_fg_1",
    91: "hi_fg_2",
    92: "hi_fg_3",
    93: "hi_fg_4",
    94: "hi_fg_5",
    95: "hi_fg_6",
    96: "hi_fg_7",
    97: "hi_fg_8",
    98: "hi_fg_9",
    99: "hi_fg_10",
})

BG.update({
    100: "hi_bg_1",
    101: "hi_bg_2",
    102: "hi_bg_3",
    103: "hi_bg_4",
    104: "hi_bg_5",
    105: "hi_bg_6",
    106: "hi_bg_7",
    107: "hi_bg_8",
    108: "hi_bg_9",
    109: "hi_bg_10",
})


class BetterScreen(pyte.Screen):
    swap_variables = [
            'mode',
            'margins',
            'charset',
            'g0_charset',
            'g1_charset',
            'tabstops',
            'cursor',
            'line_offset',
            ]

    def __init__(self, lines, columns):
        self.lines = lines
        self.columns = columns
        self.reset()

    def __before__(self, command):
        return
        logger.info('              %r' % command)

    def reset(self):
        self.buffer = defaultdict(lambda: defaultdict(lambda: Char(data=' ')))
        self.mode = set([mo.DECAWM, mo.DECTCEM])
        self.margins = Margins(0, self.lines - 1)

        self.line_offset = 0 # Index of the line that's currently displayed on top.

        # According to VT220 manual and ``linux/drivers/tty/vt.c``
        # the default G0 charset is latin-1, but for reasons unknown
        # latin-1 breaks ascii-graphics; so G0 defaults to cp437.
        self.charset = 0
        self.g0_charset = cs.IBMPC_MAP
        self.g1_charset = cs.VT100_MAP

        # From ``man terminfo`` -- "... hardware tabs are initially
        # set every `n` spaces when the terminal is powered up. Since
        # we aim to support VT102 / VT220 and linux -- we use n = 8.
        self.tabstops = set(range(7, self.columns, 8))

        self.cursor = Cursor(0, 0)
        self.cursor_position()

    def dump_character_diff(self, previous_dump):
        """
        Create a copy of the visible buffer.
        """
        space = Char(data=' ')
        result = defaultdict(lambda: defaultdict(lambda: Char(data=' ')))
        offset = self.line_offset

        def chars_eq(c1, c2):
            return c1 == c2 #or (c1.data == ' ' and c2.data == ' ') # TODO: unless they have a background or underline, etc...

        for y in range(0, self.lines):
            if (y + offset) in self.buffer:
                line = self.buffer[y + offset]
            else:
                # Empty line
                line = defaultdict(lambda: Char(data=' '))

            for x in range(0, self.columns):
                char = line.get(x, space)
                #if not previous_dump or previous_dump[y][x] != char:
                if not (previous_dump and chars_eq(previous_dump[y][x], char)):
                    result[y][x] = char

        return result

    def resize(self, lines=None, columns=None):
        # don't do anything except saving the dimensions
        self.lines = lines if lines is not None else self.lines
        self.columns = columns if columns is not None else self.columns
        self._reset_offset_and_margins()

    def _reset_offset_and_margins(self):
        """
        Recalculate offset and move cursor (make sure that the bottom is
        visible.)
        """
        self.margins = Margins(0, self.lines - 1)

        if self.buffer:
            new_line_offset = max(0, max(self.buffer.keys()) - self.lines + 4)
            self.cursor.y += (self.line_offset - new_line_offset)
            self.line_offset = new_line_offset # TODO: maybe put this in a scroll_offset function.

    def set_mode(self, *modes, **kwargs):
        # Private mode codes are shifted, to be distingiushed from non
        # private ones.
        if kwargs.get("private"):
            modes = [mode << 5 for mode in modes]

        self.mode.update(modes)

        # When DECOLM mode is set, the screen is erased and the cursor
        # moves to the home position.
        if mo.DECCOLM in modes:
            self.resize(columns=132)
            self.erase_in_display(2)
            self.cursor_position()

        # According to `vttest`, DECOM should also home the cursor, see
        # vttest/main.c:303.
        if mo.DECOM in modes:
            self.cursor_position()

        # Mark all displayed characters as reverse. # TODO !!
        if mo.DECSCNM in modes:
            for line in self.buffer.values():
                for pos, char in line.items():
                    line[pos] = char._replace(reverse=True)

            self.select_graphic_rendition(g._SGR["+reverse"])

        # Make the cursor visible.
        if mo.DECTCEM in modes:
            self.cursor.hidden = False

        # On "\e[?1049h", enter alternate screen mode. Backup the current state,
        if (1049 << 5) in modes:
            self._original_screen = self.buffer
            self._original_screen_vars = \
                { v:getattr(self, v) for v in self.swap_variables }
            self.reset()
            self._reset_offset_and_margins()

    def reset_mode(self, *modes, **kwargs):
        # Private mode codes are shifted, to be distingiushed from non
        # private ones.
        if kwargs.get("private"):
            modes = [mode << 5 for mode in modes]

        self.mode.difference_update(modes)

        # Lines below follow the logic in :meth:`set_mode`.
        if mo.DECCOLM in modes:
            self.resize(columns=80)
            self.erase_in_display(2)
            self.cursor_position()

        if mo.DECOM in modes:
            self.cursor_position()

        if mo.DECSCNM in modes: # TODO verify!!
            for line in self.buffer.values():
                for pos, char in line.items():
                    line[pos] = char._replace(reverse=False)
            self.select_graphic_rendition(g._SGR["-reverse"])

        # Hide the cursor.
        if mo.DECTCEM in modes:
            self.cursor.hidden = True

        # On "\e[?1049l", restore from alternate screen mode.
        if (1049 << 5) in modes and self._original_screen:
            for k, v in self._original_screen_vars.items():
                setattr(self, k, v)
            self.buffer = self._original_screen

            self._original_screen = None
            self._original_screen_vars = {}
            self._reset_offset_and_margins()

    def draw(self, char):
        # Translating a given character.
        char = char.translate([self.g0_charset,
                               self.g1_charset][self.charset])

        # If this was the last column in a line and auto wrap mode is
        # enabled, move the cursor to the beginning of the next line,
        # otherwise replace characters already displayed with newly
        # entered.
        if self.cursor.x == self.columns:
            if mo.DECAWM in self.mode:
                self.carriage_return()
                self.linefeed()
            else:
                self.cursor.x -= 1

        # If Insert mode is set, new characters move old characters to
        # the right, otherwise terminal is in Replace mode and new
        # characters replace old characters at cursor position.
        if mo.IRM in self.mode:
            self.insert_characters(1)

        self._set_char(self.cursor.x, self.cursor.y,
                                self.cursor.attrs._replace(data=char))

        # .. note:: We can't use :meth:`cursor_forward()`, because that
        #           way, we'll never know when to linefeed.
        self.cursor.x += 1

    def _set_char(self, x, y, char):
        self.buffer[y + self.line_offset][x] = char

    def index(self):
        """Move the cursor down one line in the same column. If the
        cursor is at the last line, create a new line at the bottom.
        """
        top, bottom = self.margins

        # When scrolling over the full screen -> keep history.
        if top == 0 and bottom == self.lines - 1:
            if self.cursor.y == self.lines - 1:
                self.line_offset += 1
            else:
                self.cursor_down()
        else:
            if self.cursor.y == bottom:
                for line in range(top, bottom):
                    self.buffer[line] = self.buffer[line+1]
                    del self.buffer[line+1]
            else:
                self.cursor_down()

    def reverse_index(self): # XXX: Used when going multiline with bash. (only second part tested.)
        top, bottom = self.margins

        # When scrolling over the full screen -> keep history.
        if self.cursor.y == top:
            for line in range(bottom, top, -1):
                self.buffer[line] = self.buffer[line-1]
                del self.buffer[line-1]
        else:
            self.cursor_up()

    def insert_lines(self, count=None):
        """Inserts the indicated # of lines at line with cursor. Lines
        displayed **at** and below the cursor move down. Lines moved
        past the bottom margin are lost.

        :param count: number of lines to delete.
        """
        count = count or 1
        top, bottom = self.margins

        # If cursor is outside scrolling margins it -- do nothin'.
        if top <= self.cursor.y <= bottom:
            #if (bottom + self.line_offset) in self.buffer:
            #    del self.buffer[bottom + self.line_offset]

            for line in range(bottom, self.cursor.y + count - 1, -1):
                self.buffer[line + self.line_offset] = self.buffer[line + self.line_offset - count]
                del self.buffer[line + self.line_offset - count]

            self.carriage_return()

    def delete_lines(self, count=None):
        """Deletes the indicated # of lines, starting at line with
        cursor. As lines are deleted, lines displayed below cursor
        move up. Lines added to bottom of screen have spaces with same
        character attributes as last line moved up.

        :param int count: number of lines to delete.
        """
        count = count or 1
        top, bottom = self.margins

        # If cursor is outside scrolling margins it -- do nothin'.
        if top <= self.cursor.y <= bottom:
            for line in range(self.cursor.y, bottom - count, -1):
                self.buffer[line + self.line_offset] = self.buffer[line + self.line_offset + count]
                del self.buffer[line + self.line_offset + count]

    def insert_characters(self, count=None): # XXX: used by pressing space in bash vi mode
        """Inserts the indicated # of blank characters at the cursor
        position. The cursor does not move and remains at the beginning
        of the inserted blank characters. Data on the line is shifted
        forward.

        :param int count: number of characters to insert.
        """
        count = count or 1

        line = self.buffer[self.cursor.y + self.line_offset]
        max_columns = max(line.keys())

        for i in range(max_columns, self.cursor.x, -1):
            line[i + count] = line[i]
            del line[i]

    def delete_characters(self, count=None): # XXX: used by pressing 'x' on bash vi mode
        count = count or 1

        line = self.buffer[self.cursor.y + self.line_offset]
        max_columns = max(line.keys())

        for i in range(self.cursor.x, max_columns):
            line[i] = line[i + count]
            del line[i + count]

    def erase_characters(self, count=None):
        raise NotImplementedError('erase_characters not implemented') # TODO

    def erase_in_line(self, type_of=0, private=False):
        """Erases a line in a specific way.

        :param int type_of: defines the way the line should be erased in:

            * ``0`` -- Erases from cursor to end of line, including cursor
              position.
            * ``1`` -- Erases from beginning of line to cursor,
              including cursor position.
            * ``2`` -- Erases complete line.
        :param bool private: when ``True`` character attributes aren left
                             unchanged **not implemented**.
        """
        def should_we_delete(column): # TODO: check for off-by-one errors!
           if type_of == 0:
                return column >= self.cursor.x
           if type_of == 1:
                return column <= self.cursor.x
           if type_of == 2:
                return True

        line = self.buffer[self.cursor.y + self.line_offset]
        for column in list(line.keys()):
           if should_we_delete(column):
               del line[column]

    def erase_in_display(self, type_of=0, private=False):
        """Erases display in a specific way.

        :param int type_of: defines the way the line should be erased in:

            * ``0`` -- Erases from cursor to end of screen, including
              cursor position.
            * ``1`` -- Erases from beginning of screen to cursor,
              including cursor position.
            * ``2`` -- Erases complete display. All lines are erased
              and changed to single-width. Cursor does not move.
        :param bool private: when ``True`` character attributes aren left
                             unchanged **not implemented**.
        """
        interval = (
            # a) erase from cursor to the end of the display, including
            # the cursor,
            range(self.cursor.y + 1, self.lines),
            # b) erase from the beginning of the display to the cursor,
            # including it,
            range(0, self.cursor.y),
            # c) erase the whole display.
            range(0, self.lines)
        )[type_of]

        for line in interval: # TODO: from where the -1 in the index below??
            self.buffer[line + self.line_offset] = defaultdict(lambda: Char(data=' '))

        # In case of 0 or 1 we have to erase the line with the cursor.
        if type_of in [0, 1]:
            self.erase_in_line(type_of)

    def alignment_display(self):
        for y in range(0, self.lines):
            line = self.buffer[y + self.line_offset]
            for x in range(0, self.columns):
                line[x] = Char('E')

    def select_graphic_rendition(self, *attrs):
        """ Support 256 colours """
        g = pyte.graphics
        replace = {}

        if not attrs:
            attrs = [0]
        else:
            attrs = list(attrs[::-1])

        while attrs:
            attr = attrs.pop()

            if attr in g.FG:
                replace["fg"] = g.FG[attr]
            elif attr in g.BG:
                replace["bg"] = g.BG[attr]
            elif attr in g.TEXT:
                attr = g.TEXT[attr]
                replace[attr[1:]] = attr.startswith("+")
            elif not attr:
                replace = self.default_char._asdict()

            elif attr in (38, 48):
                n = attrs.pop()
                if n != 5:
                    continue

                if attr == 38:
                    m = attrs.pop()
                    replace["fg"] = 1024 + m
                elif attr == 48:
                    m = attrs.pop()
                    replace["bg"] = 1024 + m

        self.cursor.attrs = self.cursor.attrs._replace(**replace)

        # See tmux/input.c, line: 1388

