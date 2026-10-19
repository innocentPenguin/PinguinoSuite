"""Connector contract. Each platform declares capabilities so the UI never offers what it cannot do."""


class Connector:
    platform = ""
    label = ""
    official = True                  # False => UI shows an UNOFFICIAL badge
    capabilities = {"read": False, "send": False, "reply": False, "badges": False, "history": False}

    def __init__(self, inbox, emit):
        self.inbox, self.emit = inbox, emit
        self.state = {"status": "disconnected", "detail": "", "reconnects": 0, "last_message": 0, "latency_ms": None}

    def set_status(self, status, detail=""):
        self.state.update(status=status, detail=detail)
        self.emit({"type": "conn.status", "platform": self.platform, **self.describe()})

    def describe(self):
        return {"platform": self.platform, "label": self.label, "official": self.official,
                "capabilities": self.capabilities, **self.state}

    async def run(self):            # long-running; reconnects internally
        raise NotImplementedError

    async def send(self, text, reply_to=None):
        raise NotImplementedError("this platform is read-only here")
