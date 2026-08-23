import unittest

from mage_maker.core.autosave import DebouncedAutosave


class _Owner:
    def __init__(self):
        self.callbacks = {}
        self.next_id = 0

    def after(self, delay, callback):
        self.next_id += 1
        callback_id = f"after-{self.next_id}"
        self.callbacks[callback_id] = (delay, callback)
        return callback_id

    def after_cancel(self, callback_id):
        self.callbacks.pop(callback_id, None)


class DebouncedAutosaveTests(unittest.TestCase):
    def test_repeated_edits_coalesce_into_one_save(self):
        owner = _Owner()
        saves = []
        autosave = DebouncedAutosave(
            owner,
            lambda: saves.append("saved") or True,
            lambda: True,
            delay_ms=700,
        )

        autosave.schedule()
        first_id = autosave.after_id
        autosave.schedule()

        self.assertNotIn(first_id, owner.callbacks)
        self.assertEqual(1, len(owner.callbacks))
        owner.callbacks[autosave.after_id][1]()
        self.assertEqual(["saved"], saves)

    def test_incomplete_record_does_not_save_or_retry_forever(self):
        owner = _Owner()
        saves = []
        autosave = DebouncedAutosave(
            owner,
            lambda: saves.append("saved") or True,
            lambda: False,
        )

        autosave.schedule()
        owner.callbacks[autosave.after_id][1]()

        self.assertEqual([], saves)
        self.assertFalse(autosave.pending)
        self.assertIsNone(autosave.after_id)


if __name__ == "__main__":
    unittest.main()