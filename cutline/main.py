from cutline.api import create_app
from cutline.logging_config import configure_logging

configure_logging()
app = create_app()
