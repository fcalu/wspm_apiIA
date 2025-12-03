import logging

logger = logging.getLogger("wspm")
logger.setLevel(logging.INFO)

# Evitar agregar múltiples handlers si se importa varias veces
if not logger.handlers:
    ch = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    ch.setFormatter(formatter)
    logger.addHandler(ch)
