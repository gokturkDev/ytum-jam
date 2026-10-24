import logging

import uvicorn

from ambassador.api.app import create_app
from ambassador.config import Settings


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # SDK HTTP debug logging may expose request bodies; keep it disabled.
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    settings = Settings()
    uvicorn.run(
        create_app(settings=settings),
        host=settings.server_host,
        port=settings.server_port,
        workers=1,
        access_log=False,
    )


if __name__ == "__main__":
    main()
