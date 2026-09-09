from cutline.cockpit_api import create_cockpit_app
from cutline.logging_config import configure_logging

configure_logging()
app = create_cockpit_app()
