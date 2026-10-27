class ValidationError(ValueError):
    """사용자 입력 오류. messages에 화면에 보여줄 문구가 들어 있다."""

    def __init__(self, messages):
        self.messages = [messages] if isinstance(messages, str) else list(messages)
        super().__init__("\n".join(self.messages))
