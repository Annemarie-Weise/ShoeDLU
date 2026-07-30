import csv
import re
from pathlib import Path


def convert_intent_csv_to_slot_csv(input_path: str, output_path: str) -> None:
    """
    Convert a semicolon-separated intent CSV into a token-level slot CSV.

    Each token is written as a separate row and initially receives the slot
    label `O` for later annotation.
    """

    input_path = Path(input_path)
    output_path = Path(output_path)

    with input_path.open("r", encoding="utf-8", newline="") as infile, \
            output_path.open("w", encoding="utf-8", newline="") as outfile:

        reader = csv.DictReader(infile, delimiter=";")
        writer = csv.DictWriter(
            outfile,
            fieldnames=["sentence_ID", "position_in_sentence", "token", "label", "intent"]
        )
        writer.writeheader()
        sentence_id = 1
        for row in reader:
            command = row["command"].strip()
            intent = row["intent"].strip()

            # Ignore empty commands rather than creating empty sentences
            if not command:
                continue

            # Punctuation was not included in the data set, but  is stripped just in case
            # The reason is that this would be too complex for the parser
            text = re.sub(r"[^\w\s%]", " ", command) # remove , . ! ? ; : ( )
            text = re.sub(r"\s+", " ", text).strip()
            tokens = text.split()
            for position, token in enumerate(tokens, start=1):
                writer.writerow({
                    "sentence_ID": sentence_id,
                    "position_in_sentence": position,
                    "token": token,
                    "label": "O",
                    "intent": intent
                })
            sentence_id += 1


if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parent

    input_file = data_dir / "intent_challenge_dataset.csv"
    output_file = data_dir / "base_slot_label_challenge_data.csv"

    convert_intent_csv_to_slot_csv(input_file, output_file)
