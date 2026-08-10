def normalized_name_key(value):
    if not isinstance(value, str):
        raise TypeError("A linked name must be text")

    return " ".join(value.split()).casefold()


def canonical_name_map(records, collection_label):
    names_by_key = {}

    for record in records:
        record_name = record.get("name", "")
        name_key = normalized_name_key(record_name)

        if not name_key:
            raise ValueError(
                f"Every {collection_label} record needs a name before "
                "it can be linked"
            )

        if name_key in names_by_key:
            raise ValueError(
                f'Duplicate {collection_label} name: "{record_name}". '
                "Name-based links require unique names."
            )

        names_by_key[name_key] = record_name.strip()

    return names_by_key


def canonical_name_choices(records, collection_label):
    names_by_key = canonical_name_map(records, collection_label)

    return sorted(names_by_key.values(), key=str.casefold)


def canonicalize_name_links(selected_names, records, collection_label):
    if not isinstance(selected_names, list):
        raise TypeError(f"Selected {collection_label} names must be a list")

    names_by_key = canonical_name_map(records, collection_label)
    selected_keys = set()
    canonical_names = []

    for selected_name in selected_names:
        name_key = normalized_name_key(selected_name)

        if name_key in selected_keys:
            raise ValueError(
                f'Duplicate selected {collection_label} name: '
                f'"{selected_name}"'
            )

        if name_key not in names_by_key:
            raise ValueError(
                f'Unknown {collection_label} name: "{selected_name}"'
            )

        selected_keys.add(name_key)
        canonical_names.append(names_by_key[name_key])

    return canonical_names


def canonicalize_name_link(selected_name, records, collection_label):
    if not isinstance(selected_name, str):
        raise TypeError(f"Selected {collection_label} name must be text")

    name_key = normalized_name_key(selected_name)

    if not name_key:
        raise ValueError(f"A {collection_label} must be selected")

    names_by_key = canonical_name_map(records, collection_label)

    if name_key not in names_by_key:
        raise ValueError(
            f'Unknown {collection_label} name: "{selected_name}"'
        )

    return names_by_key[name_key]


def ensure_unique_record_name(
    records,
    record_name,
    record_id=None,
    record_label="record",
):
    requested_key = normalized_name_key(record_name)

    for record in records:
        if record.get("record_id") == record_id:
            continue

        if normalized_name_key(record.get("name", "")) == requested_key:
            raise ValueError(
                f'A {record_label} named "{record_name.strip()}" '
                "already exists"
            )
