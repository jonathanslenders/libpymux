import logging

logger = logging.getLogger('libpymux') # __package__)


_logfile = open('/tmp/pymux-log', 'w')
logging.basicConfig(stream=_logfile, level=logging.INFO)
