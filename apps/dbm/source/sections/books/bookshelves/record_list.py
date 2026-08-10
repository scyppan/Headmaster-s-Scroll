from sections.books.books.record_list import BookList


class BookshelfList(BookList):
    def __init__(self, parent, selection_command):
        super().__init__(parent, selection_command)
        self.heading.configure(text="All Bookshelves")
        self.count_label.configure(text="0 bookshelves")

    @staticmethod
    def build_display_text(record):
        name = str(record.get("name", "")).strip() or "Unnamed bookshelf"
        book_count = len(record.get("books", []))
        book_label = "book" if book_count == 1 else "books"
        tags = [
            str(tag).strip()
            for tag in record.get("tags", [])
            if str(tag).strip()
        ]
        details = [f"{book_count} {book_label}"]

        if tags:
            details.append(", ".join(tags))

        return f"{name}\n{' • '.join(details)}"

    @staticmethod
    def build_search_text(record):
        return " ".join(
            str(value)
            for value in (
                record.get("name", ""),
                record.get("description", ""),
                " ".join(str(tag) for tag in record.get("tags", [])),
                " ".join(
                    str(reference.get("name", ""))
                    for reference in record.get("books", [])
                ),
            )
        ).casefold()

    def rebuild_visible_list(self):
        super().rebuild_visible_list()
        visible_count = len(self.visible_record_ids)
        total_count = len(self.records)

        if visible_count == total_count:
            self.count_label.configure(text=f"{total_count} bookshelves")
        else:
            self.count_label.configure(
                text=f"{visible_count} of {total_count} bookshelves"
            )
