from tkinter import messagebox


class ApplicationLifecycle:
    def __init__(self, root_window, content_host, database):
        self.root_window = root_window
        self.content_host = content_host
        self.database = database

    def close_application(self):
        if not self.content_host.can_leave_active_section():
            return

        if self.database.dirty:
            save_choice = messagebox.askyesnocancel(
                "Unsaved database changes",
                "Save database changes before closing?",
                parent=self.root_window,
            )

            if save_choice is None:
                return

            if save_choice:
                self.database.save()

        self.root_window.destroy()
