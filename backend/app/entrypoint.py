import os

import uvicorn

from app.main import app


def main() -> None:
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))
    # Default to no access log for the packaged exe; can be overridden by env.
    no_access_log = os.getenv("NO_ACCESS_LOG", "1").lower() in {"1", "true", "yes"}
    log_level = os.getenv("LOG_LEVEL")
    uvicorn.run(
        app,
        host=host,
        port=port,
        access_log=not no_access_log,
        log_level=log_level,
    )


if __name__ == "__main__":
    main()
