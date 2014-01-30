import datetime


class StatusBar:
    def __init__(self, get_client_func):
        self._get_client_func = get_client_func

    @property
    def right_text(self):
        return datetime.datetime.now().isoformat()

    @property
    def left_text(self):
        result = ['pymux']
        client = self._get_client_func()

        for w in client.windows:
            if w.active_pane:
                name = 'pid=%s' % w.active_pane.process_id
            else:
                name = '(none)'

            if client.active_window == w:
                result.append('[%s]' % name)
            else:
                result.append(' %s ' % name)

        return ' '.join(result)
