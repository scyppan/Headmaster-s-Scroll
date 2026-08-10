from database.paths import APPLICATION_DIRECTORY


TRADITIONS_PATH = APPLICATION_DIRECTORY / "data" / "traditions.txt"


def load_traditions():
    traditions = []
    normalized_traditions = set()

    with TRADITIONS_PATH.open("r", encoding="utf-8") as traditions_file:
        for tradition_line in traditions_file:
            tradition = " ".join(tradition_line.split())

            if not tradition or tradition.startswith("#"):
                continue

            normalized_tradition = tradition.casefold()

            if normalized_tradition in normalized_traditions:
                continue

            normalized_traditions.add(normalized_tradition)
            traditions.append(tradition)

    return tuple(traditions)


TRADITIONS = load_traditions()
TRADITIONS_BY_NORMALIZED_NAME = {
    tradition.casefold(): tradition for tradition in TRADITIONS
}
