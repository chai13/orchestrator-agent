from json import JSONDecodeError

import urllib3
from requests import Session

from repos.interfaces import HTTPClientRepoInterface
from tools.logger import log_error, log_info

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class HTTPClientRepo(HTTPClientRepoInterface):
    def __init__(self):
        self._session = Session()
        self._session.verify = False

    def make_request(
        self, method: str, ip: str, port: int, api: str, content: dict
    ) -> dict:
        protocol = "https" if port == 8443 else "http"
        api_path = api.lstrip("/")
        url = f"{protocol}://{ip}:{port}/{api_path}"

        log_info(f"Making {method} request to {url}")

        try:
            if method == "GET":
                response = self._session.get(url, **content)
            elif method == "POST":
                response = self._session.post(url, **content)
            elif method == "DELETE":
                response = self._session.delete(url, **content)
            elif method == "PUT":
                response = self._session.put(url, **content)
            else:
                log_error(f"Unsupported HTTP method: {method}")
                return {
                    "status_code": 400,
                    "headers": {},
                    "body": {"error": f"Unsupported HTTP method: {method}"},
                    "ok": False,
                    "content_type": "application/json",
                }

            return self._process_response(response)
        except Exception as e:
            log_error(f"Request failed: {e}")
            return {
                "status_code": 500,
                "headers": {},
                "body": {"error": str(e)},
                "ok": False,
                "content_type": "application/json",
            }

    def _process_response(self, response) -> dict:
        try:
            result = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "ok": response.ok,
            }
            try:
                result["body"] = response.json()
                result["content_type"] = "application/json"
            except JSONDecodeError:
                result["body"] = response.text
                result["content_type"] = "text/plain"
            return result
        finally:
            response.close()

    def close(self):
        self._session.close()