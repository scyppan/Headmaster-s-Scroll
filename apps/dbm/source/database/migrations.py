CURRENT_SCHEMA_VERSION = 8


def migrate_database(database_data):
    database_metadata = database_data.get("_database", {})
    schema_version = database_metadata.get("schema_version", 1)

    if schema_version > CURRENT_SCHEMA_VERSION:
        raise ValueError(
            "This database was created by a newer version of the application"
        )

    if schema_version < 2:
        for book in database_data.get("books", []):
            if isinstance(book, dict) and not str(book.get("publication_date", "") or "").strip():
                book["publication_date"] = "1900-01-01"

    if schema_version < 3:
        from headmasters_scroll.region_interactions import ensure_gathering_catalog

        ensure_gathering_catalog(database_data)

    if schema_version < 4:
        from headmasters_scroll.region_interactions import ensure_gathering_catalog

        ensure_gathering_catalog(database_data)

    if schema_version < 5:
        item_type_migrations = {
            "alchemical": "Alchemical Item",
            "divination": "Divinatory Item",
            "ritual item": "General Item",
        }
        for collection_name in (
            "general_items",
            "accessories",
            "holdable_items",
        ):
            for record in database_data.get(collection_name, []):
                if not isinstance(record, dict):
                    continue
                record.setdefault("base_knuts", 0)
                record.setdefault("actions", [])
                if collection_name == "general_items":
                    normalized_type = str(record.get("type", "")).casefold()
                    if normalized_type in item_type_migrations:
                        record["type"] = item_type_migrations[normalized_type]

    if schema_version < 6:
        database_data.setdefault("raw_materials", [])
        database_data.setdefault("recipes", [])
        # Searching methods belong only to items explicitly typed Raw Material.
        for record in database_data.get("general_items", []) or []:
            if not isinstance(record, dict):
                continue
            record.pop("extraction_method_id", None)
            if str(record.get("type", "")) != "Raw Material":
                record.pop("searching_method_id", None)
                record.pop("gathering_method_ids", None)

    if schema_version < 7:
        general_items = database_data.setdefault("general_items", [])
        existing_ids = {
            str(record.get("record_id", ""))
            for record in general_items if isinstance(record, dict)
        }
        for raw_material in database_data.get("raw_materials", []) or []:
            if not isinstance(raw_material, dict):
                continue
            record_id = str(raw_material.get("record_id", ""))
            if not record_id or record_id in existing_ids:
                continue
            migrated = dict(raw_material)
            migrated["type"] = "Raw Material"
            migrated.setdefault("bonuses", [])
            migrated.setdefault("actions", [])
            migrated.setdefault("base_knuts", 0)
            migrated.setdefault("activation_mode", "passive")
            migrated.setdefault("equipment_slot_type", "")
            general_items.append(migrated)
            existing_ids.add(record_id)
        database_data["raw_materials"] = []

    if schema_version < 8:
        output_collections = (
            "general_items", "holdable_items", "accessories", "potions",
            "preparations", "foods_and_drinks", "books",
        )
        output_by_name = {}
        for collection_name in output_collections:
            for item in database_data.get(collection_name, []) or []:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("title") or "").strip()
                record_id = str(item.get("record_id", "") or "").strip()
                if name and record_id:
                    output_by_name.setdefault(name.casefold(), {
                        "collection": collection_name,
                        "record_id": record_id,
                        "name": name,
                    })
        from uuid import uuid4
        for recipe in database_data.get("recipes", []) or []:
            if not isinstance(recipe, dict) or recipe.get("formulations"):
                continue
            output_item = recipe.get("output_item")
            if not isinstance(output_item, dict):
                output_item = output_by_name.get(str(recipe.get("name", "")).casefold())
            recipe["formulations"] = [{
                "record_id": str(uuid4()),
                "name": "Default",
                "output_item": output_item,
                "output_quantity": int(recipe.get("output_quantity", 1) or 1),
                "ingredient_requirements": recipe.get("ingredient_requirements", []) or [],
                "vessel_requirements": recipe.get("vessel_requirements", []) or [],
                "proficiency_requirements": recipe.get("proficiency_requirements", []) or [],
                "spell_requirements": recipe.get("spell_requirements", []) or [],
            }]

    database_data["_database"] = {
        **database_metadata,
        "schema_version": CURRENT_SCHEMA_VERSION,
    }

    return database_data
