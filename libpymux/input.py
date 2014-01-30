from .log import logger
from asyncio.protocols import Protocol


class InputProtocol(Protocol):
    def __init__(self, session):
        self.session = session

        self._input_parser_generator = self._input_parser()
        self._input_parser_generator.send(None)

    def connection_made(self, transport):
        self.transport = transport

    def data_received(self, data):
        self._process_input(data)

    def _process_input(self, char):
        logger.info('Received input: %r' % char)
        self._send_buffer = []

        for c in char:
            self._input_parser_generator.send(bytes((c,)))

        if self._send_buffer:
            self.session.send_input_to_current_pane(self._send_buffer)

        self._send_buffer = []

    def send_input_to_current_pane(self, data):
        self._send_buffer.append(data)

    def _input_parser(self):
        bindings = self.get_bindings()

        while True:
            char = yield

            if char == b'\x01': # Ctrl-A
                logger.info('Received CTRL-A')

                c2 = yield

                handler = bindings.get(c2, None)
                if handler:
                    handler()
            else:
                self.send_input_to_current_pane(char)

    def get_bindings(self):
        return {
            b'\x01': lambda: self.send_input_to_current_pane(b'\x01'),
        }
