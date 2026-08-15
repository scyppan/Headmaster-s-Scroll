from headmasters_scroll.effects import normalize_bonuses, validate_bonuses


def normalize_bonus_record_values(record_values):
    normalized = dict(record_values)
    if "bonuses" in normalized:
        normalized["bonuses"] = normalize_bonuses(normalized.get("bonuses"))
    return normalized


def validate_bonus_record_values(record_values):
    if "bonuses" in record_values:
        validate_bonuses(record_values.get("bonuses"))
