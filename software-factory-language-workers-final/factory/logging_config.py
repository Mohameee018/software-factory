import logging


def configure_logging(level='INFO'):
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    )
    # python-telegram-bot/httpx log full request URLs at INFO, which can include
    # the bot token. Keep operational logs useful without ever printing credentials.
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
    logging.getLogger('telegram.request').setLevel(logging.WARNING)
