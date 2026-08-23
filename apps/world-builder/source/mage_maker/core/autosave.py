"""Small Tk-friendly coordinator for valid-only, coalesced autosaves."""


class DebouncedAutosave:
    def __init__(
        self,
        owner,
        save_command,
        should_save_command=None,
        delay_ms=700,
    ):
        self.owner = owner
        self.save_command = save_command
        self.should_save_command = should_save_command
        self.delay_ms = max(100, int(delay_ms))
        self.after_id = None
        self.running = False
        self.pending = False

    def schedule(self, *unused):
        self.pending = True
        self.cancel_timer()
        try:
            self.after_id = self.owner.after(self.delay_ms, self.flush)
        except Exception:
            self.after_id = None
        return None

    def cancel_timer(self):
        if self.after_id is None:
            return
        try:
            self.owner.after_cancel(self.after_id)
        except Exception:
            pass
        self.after_id = None

    def cancel(self):
        self.pending = False
        self.cancel_timer()

    def flush(self):
        self.after_id = None
        if self.running:
            self.schedule()
            return False
        if not self.pending:
            return False
        if (
            self.should_save_command is not None
            and not self.should_save_command()
        ):
            self.pending = False
            return False

        self.pending = False
        self.running = True
        try:
            saved = bool(self.save_command())
        finally:
            self.running = False

        # Invalid/incomplete forms remain pending only after the next edit. This
        # avoids a retry loop while still saving immediately when corrected.
        return saved