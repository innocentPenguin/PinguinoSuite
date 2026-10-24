"""asyncio's last-resort handler for Listen. A browser or the app closing its socket raises ConnectionResetError (WinError 10054) inside the Windows
Proactor loop's connection_lost callback: that is the client leaving, not a fault, so it is dropped. Everything else goes to asyncio's normal handler."""

CLIENT_GONE = (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)


def handler(loop, ctx):
    if isinstance(ctx.get("exception"), CLIENT_GONE):
        return
    loop.default_exception_handler(ctx)
