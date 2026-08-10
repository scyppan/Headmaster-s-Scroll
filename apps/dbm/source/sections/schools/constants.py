SCHOOL_COURSES = (
    "Alchemy",
    "Arithmancy",
    "Artificing",
    "Astronomy",
    "Charms",
    "Creatures",
    "DarkArts",
    "Defense",
    "Divination",
    "Flying",
    "Herbology",
    "History",
    "Muggles",
    "Perception",
    "Potions",
    "Runes",
    "Social",
    "Transfiguration",
)


SCHOOL_COURSE_DISPLAY_NAMES = {
    "DarkArts": "Dark Arts",
}


SCHOOL_BOOK_SUBJECT_TO_COURSE = {
    "Ancient Runes": "Runes",
    "Dark Arts": "DarkArts",
    "Defense Against the Dark Arts": "Defense",
    "History of Magic": "History",
    "Magical Creatures": "Creatures",
    "Muggle Studies": "Muggles",
}


SCHOOL_COURSE_TO_BOOK_SUBJECT = {
    course_name: subject_name
    for subject_name, course_name in SCHOOL_BOOK_SUBJECT_TO_COURSE.items()
}


SCHOOL_BOOLEAN_OPTIONS = (
    "Yes",
    "No",
)
