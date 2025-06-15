import pandas as pd
import re
from typing import List, Optional
from loguru import logger


class NameProcessor:
    """A class to handle name processing operations for both single strings and DataFrames."""

    def __init__(self):
        self.salutations = [
            "Ms",
            "Mr",
            "Dr",
            "Mdm",
            "Mrs",
            "Dsp",
            "Miss",
            "Assoc Prof",
            "Prof",
        ]

        self.filtered_titles = [
            "PBS",
            "PPA",
            "PB",
            "NS",
            "Kepujian",
            "P",
            "CRM",
            "PBM",
            "LTC",
            "DSP",
            "SUPT",
            "PJG",
            "Do",
            "Assoc Prof",
            "Prof",
            "Adj",
            "Col",
            "So",
            "Capt",
            "Pk",
            "Dac",
            "Sac",
            "Chief Tester",
            "Asp",
            "AC",
            "Col",
            "Associate",
            "Professor",
            "Assoc",
            "Prof",
            "Adjunct",
            "Adjunct Professor",
            "Adjunct Assoc Prof",
            "Adjunct Asst Prof",
            "Asst Prof",
            "Asst",
            "Assistant Professor",
            "Assistant Assoc Prof",
            "Assistant Asst Prof",
            "Senior",
            "Snr",
            "Maj",
            "Chief",
            "Tester",
            "BBM",
        ]

        # Pre-compute lowercase versions for efficiency
        self.salutations_lower = [
            title.lower() for title in self.salutations
        ]
        self.filtered_titles_lower = [
            title.lower() for title in self.filtered_titles
        ]
        self.logger = logger

    @staticmethod
    def clean_text(text: str) -> str:
        """Clean text by removing unwanted characters and formatting."""
        if pd.isna(text) or not text:
            return ""

        # Remove words in parentheses, punctuation, numbers, and special characters
        text = re.sub(r"\([^()]*\)", "", text)
        text = re.sub(r"[^\w\s]", "", text)
        text = re.sub(r"\d+", "", text)
        text = re.sub(r"\s+", " ", text).strip().replace("\u200b", "")

        return text

    @staticmethod
    def extract_capitalized_words(text: str) -> List[str]:
        """Extract all capitalized words from text."""
        if pd.isna(text) or not text:
            return []
        return re.findall(r"\b[A-Z]+\b", str(text))

    @staticmethod
    def remove_titles_from_text(
        text: str, titles_to_remove: List[str]
    ) -> str:
        """Remove specified titles from text."""
        if pd.isna(text) or not text:
            return ""

        words = str(text).split()
        filtered_words = [
            word for word in words if word.lower() not in titles_to_remove
        ]
        return " ".join(filtered_words)

    @staticmethod
    def get_first_word_if_short(
        text: str, max_length: int = 3
    ) -> Optional[str]:
        """Get first word if it's shorter than max_length."""
        if pd.isna(text) or not text:
            return None

        words = str(text).split()
        if words and len(words[0]) < max_length:
            return words[0]
        return None

    def _process_name_core(self, name: str) -> dict:
        """Core name processing logic shared by both single and batch processing."""
        if not name or pd.isna(name):
            return {
                "raw_name": name,
                "clean_name": "",
                "capitalized_name": "",
                "lower_name": "",
                "capitalized_words": [],
                "salutation": None,
            }

        # Step 1: Store raw name and clean text
        raw_name = name
        clean_name = self.clean_text(raw_name)

        # Step 2: Check minimum length
        if len(clean_name) < 6:
            return {
                "raw_name": raw_name,
                "clean_name": clean_name,
                "capitalized_name": "",
                "lower_name": "",
                "capitalized_words": [],
                "salutation": None,
                "error": "Name too short (less than 6 characters)",
            }

        # Step 3: Create initial capitalized version and extract info
        initial_capitalized = clean_name.title()
        capitalized_words = self.extract_capitalized_words(clean_name)
        salutation = self.get_first_word_if_short(initial_capitalized)

        # Step 4: Remove salutations and filtered titles
        clean_name = self.remove_titles_from_text(
            initial_capitalized, self.salutations_lower
        )
        clean_name = self.remove_titles_from_text(
            clean_name, self.filtered_titles_lower
        )

        # Step 5: Create final formatted versions
        final_capitalized = clean_name.title()
        final_lower = clean_name.lower()

        return {
            "raw_name": raw_name,
            "clean_name": clean_name,
            "capitalized_name": final_capitalized,
            "lower_name": final_lower,
            "capitalized_words": capitalized_words,
            "salutation": salutation,
        }

    def process_single_name(self, name: str) -> dict:
        """Process a single name string and return all processed versions."""
        return self._process_name_core(name)

    def get_clean_name(self, name: str) -> str:
        """Get the cleaned name from a single name string."""
        processed = self.process_single_name(name)
        return processed.get("clean_name", "")

    def process_names(
        self, df: pd.DataFrame, name_column: str = "name"
    ) -> pd.DataFrame:
        """Process names in a DataFrame with all cleaning operations."""
        if name_column not in df.columns:
            raise ValueError(
                f"Column '{name_column}' not found in DataFrame."
            )

        if df.empty:
            self.logger.warning(
                "Input DataFrame is empty. Returning empty DataFrame."
            )
            return pd.DataFrame()

        self.logger.info(
            f"Processing {len(df)} names in column '{name_column}'."
        )
        # Apply core processing and convert to DataFrame
        processed_results = df[name_column].apply(self._process_name_core)
        results_df = pd.json_normalize(processed_results.tolist())

        # Combine with original DataFrame (excluding the name column)
        other_columns = df.drop(columns=[name_column])
        processed_df = pd.concat(
            [
                other_columns.reset_index(drop=True),
                results_df.reset_index(drop=True),
            ],
            axis=1,
        )

        # remove index column if it exists
        if "index" in processed_df.columns:
            processed_df = processed_df.drop(columns=["index"])

        # Filter out names that are too short
        processed_df = processed_df[~results_df["error"].notna()].copy()

        return processed_df


# Standalone functions for single string processing
def process_single_name(name: str) -> dict:
    """Standalone function to process a single name."""
    processor = NameProcessor()
    return processor.process_single_name(name)


def clean_single_name(name: str) -> str:
    """Standalone function to just clean a single name."""
    processor = NameProcessor()
    result = processor.process_single_name(name)
    return result.get("clean_name", "")
