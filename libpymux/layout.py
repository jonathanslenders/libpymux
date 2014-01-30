from collections import namedtuple
import weakref

from .log import logger

Location = namedtuple('Position', 'px py sx sy')


def divide_equally(available, amount):
    result = [0] * amount
    i = 0
    for _ in range(available):
        result[i] += 1
        i = (i + 1) % amount
    return result


class Container:
    def __init__(self):
        # Undefined to start with
        self.location = None

        self.children = []
        self._get_parent = lambda:None # Weakref to parent

    def __repr__(self):
        return '%s(children=%r)' % (self.__class__.__name__, self.children)

    @property
    def parent(self):
        return self._get_parent()

    def set_location(self, location):
        self.location = location
        self.resize()

    def resize(self):
        if self.location:
            for c in self.children:
                c.set_location(self.location)

    def add(self, child, replace_parent=False):
        """ Add child container. """
        if child.parent is not None and not replace_parent:
            raise Exception('%r already has a parent: %r' % (child, child.parent))

        self.children.append(child)

        # Create weak reference to parent
        child._get_parent = weakref.ref(self)

        # Trigger resize
        self.resize()

    def remove(self, child):
        self.children.remove(child)

        # Trigger resize
        self.resize()


class TileContainer(Container):
    """
    Base class for a container that can do horizontal and vertical splits.
    """
    def __init__(self):
        super().__init__()
        self.children = []
        self.sizes = [10, 10] # Initially, panes have the same size by default.

    def split(self, child, vsplit=False, after_child=None):
        """
        Split and add child.
        """
        # Create split instance
        split = VSplit() if vsplit else HSplit()
        split._get_parent = weakref.ref(self)
        assert after_child # XXX

        if after_child is None:
            index = 0
        else:
            assert after_child in self.children

            index = self.children.index(after_child)
            split.add(after_child, replace_parent=True)
            self.children[index] = split

        split.add(child)

        assert after_child.parent
        assert child.parent
        self.resize()

    def remove(self, child):
        logger.info('remove self=%r, child=%r, children=%r, parent=%r' % (self, child, self.children, self.parent))
        assert child in self.children
        self.children.remove(child)

        # When there is no child left in this container, remove this container
        # from the parent.
        if len(self.children) == 0:
            parent = self.parent
            if parent:
                self.parent.remove(self)
        # When there is only one pane left, place it in the parent container.
        elif len(self.children) == 1 and self.parent:
            logger.info('one child left. putting into parent.')

            index = self.parent.children.index(self)
            self.children[0]._get_parent = weakref.ref(self.parent)
            self.parent.children[index] = self.children[0]
            self.parent.resize()
        else:
            logger.info('two childs left. %r' % self.children)

            # Trigger resize
            self.resize()

    def resize_tile(self, direction, amount):
        """ Ignore resize requests in the base class. """

    def _divide_space(self, available_space):
        size1 = int(available_space * self.sizes[0] / sum(self.sizes))
        size2 = available_space - size1
        self.sizes = [size1, size2]


class HSplit(TileContainer):
    """ One pane at the top, one at the bottom. """
    def resize(self):
        if self.location and self.children:
            # Reserve space for the borders.
            available_space = self.location.sy - len(self.children) + 1

            # Now device equally.
            self._divide_space(available_space)
            self._apply_sizes()

    def _apply_sizes(self):
        offset = 0
        for c, size in zip(self.children, self.sizes):
            c.set_location(Location(
                    self.location.px,
                    self.location.py + offset,
                    self.location.sx,
                    size))
            offset += size + 1

    def resize_tile(self, direction, amount):
        logger.info("Resizing pane: %s %s" % (direction, amount))

        # If up/down handle here.
        if direction in ('U', 'D'):
            # Scale sizes
            sizes = self.sizes

            # Apply sizes
            if direction == 'U' and sizes[0] > 1:
                diff = min(amount, self.sizes[0] - 2) # Minimum pane size.
                self.sizes = [sizes[0] - diff, sizes[1] + diff]
                self._apply_sizes()
            if direction == 'D' and sizes[1] > 1:
                diff = min(amount, self.sizes[1] - 2)
                self.sizes = [sizes[0] + diff, sizes[1] - diff]
                self._apply_sizes()

        # Otherwise, handle in parent.
        elif self.parent:
            logger.info('go to parent. in vsplit..')
            self.parent.resize_tile(direction, amount)


class VSplit(TileContainer):
    """ One pane at the left, one at the right. """
    def resize(self):
        if self.location and self.children:# TODO: assert len(self.children) == 2
            # Reserve space for the borders.
            available_space = self.location.sx - len(self.children) + 1

            # Now device equally.
            self._divide_space(available_space)
            self._apply_sizes()

    def _apply_sizes(self):
        offset = 0
        for c, size in zip(self.children, self.sizes):
            c.set_location(Location(
                    self.location.px + offset,
                    self.location.py,
                    size,
                    self.location.sy))
            offset += size + 1

    def resize_tile(self, direction, amount):
        logger.info("Resizing pane: %s %s" % (direction, amount))

        # If up/down handle here.
        if direction in ('L', 'R'):
            # Scale sizes
            sizes = self.sizes

            # Apply sizes
            if direction == 'L' and sizes[0] > 1:
                diff = min(amount, self.sizes[0] - 2) # Minimum pane size.
                self.sizes = [sizes[0] - diff, sizes[1] + diff]
                self._apply_sizes()
            if direction == 'R' and sizes[1] > 1:
                diff = min(amount, self.sizes[1] - 2)
                self.sizes = [sizes[0] + diff, sizes[1] - diff]
                self._apply_sizes()

        # Otherwise, handle in parent.
        elif self.parent:
            logger.info('go to parent. in hsplit..')
            self.parent.resize_tile(direction, amount)

