import ctypes
import sys
import traceback
from pathlib import Path


def run_application(app_class=None):
    try:
        if app_class is None:
            from app import App

            resolved_app_class = App
        else:
            resolved_app_class = app_class

        application = resolved_app_class()
        application.mainloop()
        return True
    except Exception as error:
        crash_details = traceback.format_exc()
        crash_log_path = Path(__file__).resolve().with_name(
            "world-builder-crash.log"
        )

        try:
            crash_log_path.write_text(crash_details, encoding="utf-8")
        except OSError:
            pass

        error_message = (
            f"World Builder could not start.\n\n"
            f"{type(error).__name__}: {error}\n\n"
            f"Details were saved to:\n{crash_log_path}"
        )

        if sys.platform == "win32":
            try:
                user32 = ctypes.WinDLL("user32", use_last_error=True)
                show_message = user32.MessageBoxW
                show_message.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_wchar_p,
                    ctypes.c_wchar_p,
                    ctypes.c_uint,
                ]
                show_message.restype = ctypes.c_int
                show_message(
                    None,
                    error_message,
                    "World Builder could not start",
                    0x00000010,
                )
            except (AttributeError, OSError, TypeError, ValueError):
                print(error_message, file=sys.stderr)
        else:
            print(error_message, file=sys.stderr)

        return False
