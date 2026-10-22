def profile_data(df):
    profile = {
        "total_rows": len(df),
        "total_columns": len(df.columns),
        "missing_values": int(df.isnull().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()),
    }

    print("\n=== DATA PROFILE ===")
    print(f"Total baris       : {profile['total_rows']}")
    print(f"Total kolom       : {profile['total_columns']}")
    print(f"Nilai kosong      : {profile['missing_values']}")
    print(f"Baris duplikat    : {profile['duplicate_rows']}")

    return profile
