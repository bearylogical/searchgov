import polars as pl
import pytest
from preprocess.clean import (
    clean_text,
    extract_capitalized_words,
    extract_capitalized_words_vectorized,
    clean_names,
)


def test_clean_text():
    assert clean_text("Hello (world)! 123") == "Hello world"
    assert (
        clean_text("This is a test. (Remove this) 456!")
        == "This is a test Remove this"
    )
    assert clean_text("No special chars!@#") == "No special chars"
    assert clean_text("Whitespace   test") == "Whitespace test"
    assert clean_text("Zero-width\u200bspace") == "Zero widthspace"
    assert clean_text("") == ""


def test_extract_capitalized_words():
    assert extract_capitalized_words("This is a TEST") == ["TEST"]
    assert extract_capitalized_words("Another TEST CASE") == [
        "TEST",
        "CASE",
    ]
    assert extract_capitalized_words("No Capitals") == []
    assert extract_capitalized_words("") == []
    assert extract_capitalized_words(None) == []


def test_extract_capitalized_words_vectorized():
    series = pl.Series(
        [
            "Low Thia KIANG test",
            "Mr Lee HSIEN Loong jack",
            None,
            "Test CASE small",
        ]
    )
    assert extract_capitalized_words_vectorized(series) == [
        "Low Thia KIANG",
        "Lee HSIEN Loong",
        "Test CASE",
    ]


def test_clean_names():
    df = pl.DataFrame(
        {
            "raw_name": [
                "John Doe",
                "Jane (Smith)",
                "ALICE",
                "Bob",
                "CHARLIE BROWN",
                "Dr. John Doe",
                "Ms. Jane Smith",
                "Prof. Alice",
                "Mr. Bob",
                "Mrs. Charlie Brown",
                "John Doe (PBS)",
                "Jane Smith (PPA)",
                "Alice (PB)",
                "Bob (NS)",
                "Charlie Brown (Kepujian)",
            ]
        }
    )
    cleaned_df = clean_names(df)

    assert "clean_name" in cleaned_df.columns
    assert "lower_name" in cleaned_df.columns
    assert "capitalized_name" in cleaned_df.columns
    assert "capitalized_words" in cleaned_df.columns

    assert cleaned_df["clean_name"].to_list() == [
        "John Doe",
        "Jane Smith",
        "Charlie Brown",
        "John Doe",
        "Jane Smith",
        "Alice",
        "Bob",
        "Charlie Brown",
        "John Doe",
        "Jane Smith",
        "Alice",
        "Bob",
        "Charlie Brown",
    ]
    assert cleaned_df["lower_name"].to_list() == [
        "john doe",
        "jane smith",
        "charlie brown",
        "john doe",
        "jane smith",
        "alice",
        "bob",
        "charlie brown",
        "john doe",
        "jane smith",
        "alice",
        "bob",
        "charlie brown",
    ]
    assert cleaned_df["capitalized_name"].to_list() == [
        "John Doe",
        "Jane Smith",
        "Charlie Brown",
        "John Doe",
        "Jane Smith",
        "Alice",
        "Bob",
        "Charlie Brown",
        "John Doe",
        "Jane Smith",
        "Alice",
        "Bob",
        "Charlie Brown",
    ]
    assert cleaned_df["capitalized_words"].to_list() == [
        [],
        [],
        ["CHARLIE", "BROWN"],
        [],
        [],
        [],
        [],
        [],
        ["PBS"],
        ["PPA"],
        ["PB"],
        ["NS"],
        [],
    ]


if __name__ == "__main__":
    pytest.main()
