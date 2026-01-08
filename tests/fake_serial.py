class FakeSerial:
    def __init__(self, responses=None):
        self.responses = responses or []
        self.is_open = True
        self.written = []

    def write(self, data):
        self.written.append(data)

    def read(self, size=1024):
        if not self.responses:
            return b""
        return self.responses.pop(0)

    def close(self):
        self.is_open = False
