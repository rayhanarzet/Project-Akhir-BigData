def select_pipeline(profile):
    if (
        profile["missing_values"] > 0
        or profile["duplicate_rows"] > 0
    ):
        return "CLEANING"

    return "STANDARD"
