

class Redraw:
    """ Invalidate bitmasks. """
    Nothing = 0
    Cursor = 1
    Borders = 2
    Panes = 4
    StatusBar = 16
    ClearFirst = 32

    All = Cursor | Borders | Panes | StatusBar | ClearFirst
