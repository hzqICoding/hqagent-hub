import logging
import os

import uvicorn


def main():
    logging.basicConfig(level=logging.INFO, format="%(name)s %(message)s")
    # Never run multiple workers against this single-process SQLite deployment.
    uvicorn.run("server.app:create_app", factory=True,
                host=os.environ.get("HQREMOTE_HOST", "127.0.0.1"),
                port=int(os.environ.get("HQREMOTE_PORT", "8080")),
                workers=1, access_log=False, ws_max_size=262144,
                proxy_headers=True,
                forwarded_allow_ips=os.environ.get("HQREMOTE_PROXY_IPS", "127.0.0.1"))


if __name__ == "__main__":
    main()
