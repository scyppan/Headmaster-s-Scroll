from copy import deepcopy

from sections.schools.constants import (
    SCHOOL_BOOK_SUBJECT_TO_COURSE,
    SCHOOL_COURSE_DISPLAY_NAMES,
    SCHOOL_COURSES,
)


class SchoolController:
    collection_name = "schools"
    text_fields = (
        "name",
        "location",
        "description",
        "areas_served",
        "philosophy_and_practice",
        "architecture",
        "dbnotes",
    )

    def __init__(self, database):
        self.database = database

    def list_records(self):
        records = self.database.get_collection(self.collection_name)
        records.sort(key=self.record_sort_key)

        return records

    def get_record(self, record_id):
        return self.database.read(self.collection_name, record_id)

    def create_record(self, record_values):
        complete_values = {
            "name": "",
            "location": "",
            "canon": False,
            "wandless": False,
            "description": "",
            "areas_served": "",
            "philosophy_and_practice": "",
            "architecture": "",
            "curriculum": self.empty_curriculum(),
            "course_books": [],
            "dbnotes": "",
        }
        complete_values.update(deepcopy(record_values))
        normalized_values = self.normalize_record_values(complete_values)
        self.validate_record_values(normalized_values)
        created_record = self.database.create(
            self.collection_name,
            normalized_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
        current_record = self.get_record(record_id)

        if current_record is None:
            raise KeyError(f"Unknown school record ID: {record_id}")

        normalized_changes = self.normalize_record_values(record_values)
        prospective_record = deepcopy(current_record)
        prospective_record.update(normalized_changes)
        self.validate_record_values(prospective_record)
        updated_record = self.database.update(
            self.collection_name,
            record_id,
            normalized_changes,
        )
        self.database.save()

        return updated_record

    def delete_record(self, record_id):
        deleted_record = self.database.delete(
            self.collection_name,
            record_id,
        )
        self.database.save()

        return deleted_record

    def normalize_record_values(self, record_values):
        normalized_values = deepcopy(record_values)

        for field_name in self.text_fields:
            if field_name in normalized_values:
                normalized_values[field_name] = str(
                    normalized_values[field_name] or ""
                ).strip()

        for field_name in ("canon", "wandless"):
            if field_name in normalized_values:
                normalized_values[field_name] = self.normalize_boolean(
                    normalized_values[field_name],
                    field_name,
                )

        if "curriculum" in normalized_values:
            normalized_values["curriculum"] = self.normalize_curriculum(
                normalized_values["curriculum"]
            )

        if "course_books" in normalized_values:
            normalized_values["course_books"] = self.normalize_course_books(
                normalized_values["course_books"]
            )

        return normalized_values

    def normalize_boolean(self, value, field_name):
        if isinstance(value, bool):
            return value

        normalized_value = str(value or "").strip().casefold()

        if normalized_value in ("yes", "true", "1"):
            return True

        if normalized_value in ("no", "false", "0"):
            return False

        raise ValueError(f"School {field_name} must be Yes or No.")

    def normalize_curriculum(self, curriculum):
        if not isinstance(curriculum, list):
            raise TypeError("School curriculum must be a list.")

        normalized_curriculum = []

        for year_index, year_record in enumerate(curriculum):
            if not isinstance(year_record, dict):
                raise TypeError("Every school year must be an object.")

            normalized_curriculum.append(
                {
                    "year": year_index + 1,
                    "core": self.normalize_course_list(
                        year_record.get("core", []),
                        "core",
                    ),
                    "electives": self.normalize_course_list(
                        year_record.get("electives", []),
                        "elective",
                    ),
                    "elective_limit": self.normalize_elective_limit(
                        year_record.get("elective_limit", 0)
                    ),
                }
            )

        return normalized_curriculum

    def normalize_course_list(self, courses, list_name):
        if not isinstance(courses, list):
            raise TypeError(f"School {list_name} courses must be a list.")

        normalized_courses = []

        for course in courses:
            course_text = " ".join(str(course).split())
            canonical_course = self.normalize_course_name(course_text)

            if canonical_course is None:
                raise ValueError(f"Unknown school course: {course_text}")

            normalized_courses.append(canonical_course)

        return normalized_courses

    def normalize_course_name(self, course_name):
        course_names = {
            canonical_name.casefold(): canonical_name
            for canonical_name in SCHOOL_COURSES
        }

        for canonical_name, display_name in (
            SCHOOL_COURSE_DISPLAY_NAMES.items()
        ):
            course_names[display_name.casefold()] = canonical_name

        for subject_name, canonical_name in (
            SCHOOL_BOOK_SUBJECT_TO_COURSE.items()
        ):
            course_names[subject_name.casefold()] = canonical_name

        return course_names.get(str(course_name).casefold())

    def normalize_elective_limit(self, elective_limit):
        if elective_limit in (None, ""):
            return 0

        if isinstance(elective_limit, bool):
            raise TypeError("School elective limits must be whole numbers.")

        try:
            normalized_limit = int(elective_limit)
        except (TypeError, ValueError) as error:
            raise TypeError(
                "School elective limits must be whole numbers."
            ) from error

        return normalized_limit

    def normalize_course_books(self, course_books):
        if not isinstance(course_books, list):
            raise TypeError("School course books must be a list.")

        normalized_course_books = []

        for course_book in course_books:
            if not isinstance(course_book, dict):
                raise TypeError("Every school course book must be an object.")

            year = self.normalize_course_book_year(
                course_book.get("year")
            )
            course_text = " ".join(
                str(
                    course_book.get(
                        "course",
                        course_book.get("subject", ""),
                    )
                ).split()
            )
            course = self.normalize_course_name(course_text)

            if course is None:
                raise ValueError(f"Unknown school course: {course_text}")

            record_id = str(course_book.get("record_id", "")).strip()
            normalized_course_books.append(
                {
                    "year": year,
                    "course": course,
                    "record_id": record_id,
                }
            )

        return normalized_course_books

    def normalize_course_book_year(self, year):
        if isinstance(year, bool):
            raise TypeError("School course-book years must be whole numbers.")

        try:
            normalized_year = int(year)
        except (TypeError, ValueError) as error:
            raise TypeError(
                "School course-book years must be whole numbers."
            ) from error

        return normalized_year

    def validate_record_values(self, record_values):
        if not record_values.get("name", "").strip():
            raise ValueError("A school must have a name.")

        for field_name in self.text_fields:
            if field_name in record_values and not isinstance(
                record_values[field_name],
                str,
            ):
                raise TypeError(f"School {field_name} must be text.")

        for field_name in ("canon", "wandless"):
            if not isinstance(record_values.get(field_name), bool):
                raise TypeError(f"School {field_name} must be true or false.")

        self.validate_curriculum(record_values.get("curriculum", []))
        self.validate_course_books(
            record_values.get("course_books", []),
            record_values.get("curriculum", []),
        )

    def validate_curriculum(self, curriculum):
        if not isinstance(curriculum, list) or len(curriculum) != 7:
            raise ValueError("A school curriculum must contain Years 1–7.")

        for year_number, year_record in enumerate(curriculum, start=1):
            if not isinstance(year_record, dict):
                raise TypeError("Every school year must be an object.")

            if year_record.get("year") != year_number:
                raise ValueError("School curriculum years must remain in order.")

            for list_name in ("core", "electives"):
                course_list = year_record.get(list_name)

                if not isinstance(course_list, list):
                    raise TypeError(
                        f"School Year {year_number} {list_name} must be a list."
                    )

                normalized_names = set()

                for course_name in course_list:
                    if course_name not in SCHOOL_COURSES:
                        raise ValueError(
                            f"Unknown school course: {course_name}"
                        )

                    normalized_name = course_name.casefold()

                    if normalized_name in normalized_names:
                        raise ValueError(
                            f"Duplicate Year {year_number} course: {course_name}"
                        )

                    normalized_names.add(normalized_name)

            elective_limit = year_record.get("elective_limit")

            if not isinstance(elective_limit, int) or isinstance(
                elective_limit,
                bool,
            ):
                raise TypeError("School elective limits must be whole numbers.")

            if elective_limit < 0:
                raise ValueError("School elective limits cannot be negative.")

            if elective_limit > len(year_record.get("electives", [])):
                raise ValueError(
                    f"Year {year_number} elective limit exceeds its choices."
                )

    def validate_course_books(self, course_books, curriculum):
        if not isinstance(course_books, list):
            raise TypeError("School course books must be a list.")

        book_ids = {
            book.get("record_id")
            for book in self.database.get_collection("books")
        }

        for course_book in course_books:
            if not isinstance(course_book, dict):
                raise TypeError("Every school course book must be an object.")

            year = course_book.get("year")

            if not isinstance(year, int) or isinstance(year, bool):
                raise TypeError(
                    "School course-book years must be whole numbers."
                )

            if year < 1 or year > 7:
                raise ValueError("School course-book years must be 1–7.")

            course = course_book.get("course")

            if course not in SCHOOL_COURSES:
                raise ValueError(f"Unknown school course: {course}")

            year_record = curriculum[year - 1]
            selected_courses = set(year_record.get("core", []))
            selected_courses.update(year_record.get("electives", []))

            if course not in selected_courses:
                raise ValueError(
                    f"Year {year} course book belongs to an unchecked "
                    f"course: {course}"
                )

            record_id = course_book.get("record_id", "")

            if not isinstance(record_id, str) or not record_id.strip():
                raise ValueError("Every school course book needs a book ID.")

            if record_id not in book_ids:
                raise ValueError(
                    f"Unknown school course book: "
                    f"{course_book.get('name', record_id)}"
                )

            if not isinstance(course_book.get("name", ""), str):
                raise TypeError("Every school course book name must be text.")

    @staticmethod
    def empty_curriculum():
        return [
            {
                "year": year_number,
                "core": [],
                "electives": [],
                "elective_limit": 0,
            }
            for year_number in range(1, 8)
        ]

    @staticmethod
    def record_sort_key(record):
        return (
            record.get("name", "").casefold(),
            record.get("record_id", ""),
        )
