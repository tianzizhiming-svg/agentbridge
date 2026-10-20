import logging
logger = logging.getLogger(__name__)


class UTF8BodyMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        method = scope.get("method", "")
        if method not in ("POST", "PUT", "PATCH"):
            await self.app(scope, receive, send)
            return
        is_json = False
        for name, value in scope.get("headers", []):
            if name == b"content-type" and b"json" in value.lower():
                is_json = True
                break
        if not is_json:
            await self.app(scope, receive, send)
            return
        body_parts = []
        while True:
            msg = await receive()
            if msg["type"] == "http.request":
                body_parts.append(msg.get("body", b""))
                if not msg.get("more_body", False):
                    break
        full_body = b"".join(body_parts)
        try:
            full_body.decode("utf-8")
        except UnicodeDecodeError:
            for enc in ("gb2312", "gbk", "windows-1252", "latin-1"):
                try:
                    text = full_body.decode(enc)
                    full_body = text.encode("utf-8")
                    logger.info(f"Re-encoded request body from {enc} to UTF-8")
                    break
                except (UnicodeDecodeError, UnicodeEncodeError):
                    continue
        async def receive_wrapper():
            return {"type": "http.request", "body": full_body, "more_body": False}
        await self.app(scope, receive_wrapper, send)
