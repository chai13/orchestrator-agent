from use_cases.runtime_commands import make_request

from repos.interfaces import HTTPClientRepoInterface


class HTTPClientRepo(HTTPClientRepoInterface):
    """Concrete repo wrapping the requests-based HTTP client."""

    def make_request(
        self, method: str, ip: str, port: int, api: str, content: dict
    ) -> dict:
        return make_request(method, ip, port, api, content)
