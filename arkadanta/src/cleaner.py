def clean_data(df):
    original_rows = len(df)

    # Menghapus baris yang seluruh nilainya kosong
    df = df.dropna(how="all")

    # Menghapus baris duplikat
    df = df.drop_duplicates()

    removed_rows = original_rows - len(df)

    print("\n=== DATA CLEANING ===")
    print(f"Baris sebelum cleaning : {original_rows}")
    print(f"Baris sesudah cleaning : {len(df)}")
    print(f"Baris dihapus          : {removed_rows}")

    return df
