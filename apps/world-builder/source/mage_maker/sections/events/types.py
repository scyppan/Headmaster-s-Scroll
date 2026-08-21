EVENT_TYPE_DEFINITIONS = (
    ("starting_location", "Starting location", ("person",), True),
    ("born", "Birth event", ("person",), False),
    ("birth_name", "Birth name", ("person",), True),
    ("gave_birth", "Gave birth", ("person",), True),
    ("had_child", "Had a child", ("person",), True),
    ("got_married", "Marriage", ("person",), False),
    ("romance", "Romance", ("person",), False),
    ("breakup", "Breakup", ("person",), False),
    ("died", "Death", ("person",), False),
    ("murder", "Murder", ("person",), False),
    ("returns_as_ghost", "Returns as ghost", ("person",), False),
    ("started_school", "Started school", ("person",), False),
    ("opened_business", "Opened a business", ("person",), False),
    ("started_job", "Started job", ("person",), False),
    ("received_raise", "Received a raise", ("person",), False),
    ("began_friendship", "Began friendship", ("person",), False),
    # Foster care is authored from the Relationships tab because it needs
    # explicit parent/child roles.  Existing foster events remain editable
    # from the general event editor once selected.
    ("foster_child", "Foster child", ("relationship",), False),
    ("taught_spell", "Taught a spell", ("person",), False),
    ("taught_proficiency", "Taught a proficiency", ("person",), False),
    ("taught_recipe", "Taught a recipe", ("person",), False),
    ("tamed_creature", "Tamed a creature", ("person",), False),
    ("bonded_creature", "Bonded with a creature", ("person",), False),
    ("irked_creature", "Irked a creature", ("person",), False),
    ("joined_faction", "Joined a faction", ("person",), False),
    ("left_faction", "Left a faction", ("person",), False),
    ("work_change", "Change in work", ("person",), False),
    ("relocated", "Relocated", ("person",), False),
    ("travel", "Travel", ("person",), False),
    ("crafted", "Crafted", ("person",), False),
    (
        "published_book",
        "Published a book",
        ("person", "book"),
        False,
    ),
    ("item_event", "Item event", ("person", "item"), False),
    ("gifted", "Gifted", ("person", "item"), False),
    ("destroyed", "Destroyed", ("item",), False),
    ("name_change", "Name change", ("person",), False),
    ("custom", "Custom event", ("person",), False),
    (
        "founding",
        "Founding a location",
        ("person", "location"),
        False,
    ),
    (
        "organization_founding",
        "Founding an organization",
        ("organization",),
        False,
    ),
    (
        "wizarding_community_established",
        "Wizarding community established",
        ("location",),
        False,
    ),
    ("extinction", "Extinction", ("location",), False),
    ("political", "Political", ("location",), False),
    ("conflict", "Conflict", ("location",), False),
    ("discovery", "Discovery", ("person", "location"), False),
    ("education", "Education", ("location",), False),
    ("cultural", "Cultural", ("location",), False),
    ("disaster", "Disaster", ("location",), False),
    (
        "address_owner_changed",
        "New owner",
        ("location",),
        False,
    ),
    (
        "address_occupancy_changed",
        "New occupant",
        ("location",),
        False,
    ),
    (
        "address_contents_changed",
        "New inventory",
        ("location",),
        False,
    ),
    ("other", "General event", ("location",), False),
)
EVENT_TYPE_LABELS = {
    event_type: label
    for event_type, label, contexts, automatic in EVENT_TYPE_DEFINITIONS
}
EVENT_LABEL_TYPES = {
    label: event_type
    for event_type, label, contexts, automatic in EVENT_TYPE_DEFINITIONS
}
EVENT_LABEL_TYPES.update(
    {
        "Got married": "got_married",
        "Born": "born",
        "Birth": "born",
        "Died": "died",
        "Returned as ghost": "returns_as_ghost",
        "Started at school": "started_school",
        "Got a job": "started_job",
        "Founding": "founding",
    }
)
LEGACY_EVENT_TYPE_ALIASES = {
    "birth": "born",
    "death": "died",
    "murder": "murder",
    "returned as ghost": "returns_as_ghost",
    "returns as ghost": "returns_as_ghost",
    "marriage": "got_married",
    "romance": "romance",
    "breakup": "breakup",
    "got_job": "started_job",
    "got a job": "started_job",
    "got job": "started_job",
    "started job": "started_job",
    "received a raise": "received_raise",
    "began friendship": "began_friendship",
    "foster child": "foster_child",
    "fostered a child": "foster_child",
    "extinct": "extinction",
    "extinction": "extinction",
    "relocation": "relocated",
    "travel": "travel",
    "crafted": "crafted",
    "item": "item_event",
    "item event": "item_event",
    "gifted": "gifted",
    "destroyed": "destroyed",
    "wizarding community established": (
        "wizarding_community_established"
    ),
}
HIDDEN_OUTSIDE_PERSON_EVENT_TYPES = {
    "starting_location",
    "birth_name",
}


def canonical_event_type(event_type):
    normalized = str(event_type or "").strip()
    return LEGACY_EVENT_TYPE_ALIASES.get(
        normalized,
        LEGACY_EVENT_TYPE_ALIASES.get(
            normalized.casefold(),
            normalized,
        ),
    )


def event_type_label(event_or_type):
    if isinstance(event_or_type, dict):
        requested_type = event_or_type.get("event_type")
    else:
        requested_type = event_or_type

    normalized_type = canonical_event_type(requested_type)
    return EVENT_TYPE_LABELS.get(normalized_type, "General event")


def event_type_from_label(label, fallback="other"):
    return EVENT_LABEL_TYPES.get(str(label or "").strip(), fallback)


def event_type_options(
    context,
    include_automatic=False,
    current_event_type="",
):
    normalized_context = str(context or "").strip().casefold()
    options = []

    for event_type, label, contexts, automatic in EVENT_TYPE_DEFINITIONS:
        if automatic and not include_automatic:
            continue

        if (
            normalized_context == "item"
            and event_type in ("born", "died")
        ):
            continue

        if (
            normalized_context in ("period", "item")
            or normalized_context in contexts
        ):
            options.append((event_type, label))

    current_type = canonical_event_type(current_event_type)

    if current_type and current_type in EVENT_TYPE_LABELS:
        current_option = (current_type, EVENT_TYPE_LABELS[current_type])

        if current_option not in options:
            options.insert(0, current_option)

    return tuple(options)


def event_type_contexts(event_type):
    normalized_type = canonical_event_type(event_type)

    for candidate_type, label, contexts, automatic in EVENT_TYPE_DEFINITIONS:
        if candidate_type == normalized_type:
            return tuple(contexts)

    return ()


def event_type_is_automatic(event_type):
    normalized_type = canonical_event_type(event_type)

    for candidate_type, label, contexts, automatic in EVENT_TYPE_DEFINITIONS:
        if candidate_type == normalized_type:
            return bool(automatic)

    return False


def event_type_is_person_only(event_type):
    return event_type_contexts(event_type) == ("person",)


def event_visible_outside_person(event_type):
    return (
        canonical_event_type(event_type)
        not in HIDDEN_OUTSIDE_PERSON_EVENT_TYPES
    )
