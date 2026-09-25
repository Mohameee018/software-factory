import logging
def configure_logging(level='INFO'): logging.basicConfig(level=getattr(logging,level,logging.INFO),format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
