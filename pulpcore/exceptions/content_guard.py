class AuthenticationError(Exception):
    """Raised when a content guard requires the client to authenticate."""

    def __init__(self, message="Authentication required.", *, challenge):
        super().__init__(message)
        self.challenge = challenge
