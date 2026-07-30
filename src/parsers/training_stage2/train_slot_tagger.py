"""Train and evaluate the CRF slot tagger for shoe-world commands.

The script loads and cleans token-level slot-labeling data, converts each
sentence into CRF features, trains a sequence-labeling model, evaluates it
on a stratified test split, and saves the trained model.

Run from the project root with:
python -m src.parsers.training_stage2.train_slot_tagger
"""

from pathlib import Path
import sys
from datetime import datetime
from typing import Any, Dict, List

import joblib
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn_crfsuite import CRF, metrics

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain_rules_and_constants import VALID_INTENTS
from .slot_features import sentence_to_features


DATA_DIR = PROJECT_ROOT / "data" / "model_training_data"
MODEL_DIR = PROJECT_ROOT / "models"
LOG_DIR = PROJECT_ROOT / "evaluation_results" / "model_training_logs"
DATA_PATH = DATA_DIR / "slot_labeling_training_dataset.csv"

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
LOG_PATH = LOG_DIR / f"slot_tagger_crf_training_log_{timestamp}.log"



def log(message: object = "") -> None:
    """Print a message and append it to the training log file."""

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    message = str(message)
    print(message)

    with open(LOG_PATH, "a", encoding="utf-8") as file:
        file.write(message + "\n")



def load_slot_label_dataset(path: Path) -> pd.DataFrame:
    """Load and clean the token-level slot-labeling dataset."""

    data = pd.read_csv(path, sep=",")

    # Remove incomplete rows and normalize column types and whitespace
    data = data.dropna(subset=["sentence_ID", "intent", "token", "label"])
    data["sentence_ID"] = data["sentence_ID"].astype(int)
    data["intent"] = data["intent"].astype(str).str.strip()
    data["token"] = data["token"].astype(str).str.strip()
    data["label"] = data["label"].astype(str).str.strip()

    # Keep only intents supported by the shoe-world system
    data = data[data["intent"].isin(VALID_INTENTS)]

    # Remove rows with empty tokens or slot labels
    data = data[data["token"] != ""]
    data = data[data["label"] != ""]
    return data

    

def group_sentences(data: pd.DataFrame) -> List[Dict[str, Any]]:
    """Group token-level rows into sentence dictionaries for CRF training."""

    sentences = []
    for sentence_id, group in data.groupby("sentence_ID", sort=True):
        intents = group["intent"].unique()
        sentence = {
            "sentence_ID": sentence_id,
            "intent": intents[0],
            "tokens": group["token"].tolist(),
            "labels": group["label"].tolist()
        }
        sentences.append(sentence)
    return sentences



def evaluate_predictions(
    title: str,
    sentences: List[Dict[str, Any]],
    gold_labels: List[List[str]],
    predicted_labels: List[List[str]]
) -> None:
    """Log token-level evaluation results for predicted slot labels."""

    labels = sorted(
        set(label for sentence in gold_labels for label in sentence)
        | set(label for sentence in predicted_labels for label in sentence)
    )

    # Exclude the frequent outside label so it does not dominate the slot score
    if "O" in labels:
        labels.remove("O")

    log("\n" + "#" * 100 + f"\n{title}\n" + "#" * 100)
    log(f"Sentences: {len(sentences)}\n")
    log("Token-level evaluation without O label:")
    log(
        f"Weighted F1: "
        f"{metrics.flat_f1_score(
            gold_labels,
            predicted_labels,
            average='weighted',
            labels=labels,
            zero_division=0
        ):.4f}"
    )
    log("\nClassification report:")
    log(
        metrics.flat_classification_report(
            gold_labels,
            predicted_labels,
            labels=labels,
            digits=4,
            zero_division=0
        )
    )

    

def train_model(sentences: List[Dict[str, Any]]):
    """Train a CRF slot tagger and evaluate it on a random test split."""

    intent_labels_for_stratify = [
        sentence["intent"]
        for sentence in sentences
    ]

    sentence_train, sentence_test = train_test_split(
        sentences,
        test_size=0.25,  # Use 25% of sentences for testing
        random_state=404,  # Fixed seed for reproducible results
        stratify=intent_labels_for_stratify  # Keep intent distribution similar in train and test data
    )

    # Convert token sequences into CRF feature dictionaries
    command_train = [sentence_to_features(sentence) for sentence in sentence_train]
    token_label_train = [sentence["labels"] for sentence in sentence_train]
    command_test = [sentence_to_features(sentence) for sentence in sentence_test]
    token_label_test = [sentence["labels"] for sentence in sentence_test]

    # Create sequence-labeling model
    classifier = CRF(
        algorithm="lbfgs",  # General-purpose optimizer
        c1=0.1,  # L1 regularization: encourages ignoring weak features
        c2=0.1,  # L2 regularization: discourages overly large weights
        max_iterations=100,
        all_possible_transitions=True
    )

    # Train on token features and gold slot labels
    classifier.fit(command_train, token_label_train)
    # Predict slot labels for the held-out test sentences
    token_label_pred = classifier.predict(command_test)

    log("#" * 100 + "\nCRF Slot Tagging Results\n" + "#" * 100)
    log(f"Training sentences: {len(sentence_train)}")
    log(f"Test sentences:     {len(sentence_test)}\n")

    evaluate_predictions(
        title="Random Test Split Evaluation",
        sentences=sentence_test,
        gold_labels=token_label_test,
        predicted_labels=token_label_pred
    )

    log("\nAll labels learned by the CRF:")
    log(classifier.classes_)
    return classifier



def save_model(classifier) -> None:
    """Save the trained CRF slot tagger to the model directory."""

    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    classifier_path = MODEL_DIR / "slot_tagger_crf.joblib"
    joblib.dump(classifier, classifier_path)
        


def main():
    """Run the complete slot-tagger training and evaluation pipeline."""

    data = load_slot_label_dataset(DATA_PATH)

    log("#" * 100 + "\nLoaded slot-label dataset\n" + "#" * 100)
    log(f"Total token rows after cleanup: {len(data)}")
    log(f"Total sentences: {data['sentence_ID'].nunique()}\n")
    log("Intent distribution by sentence:")
    sentence_level_data = data.drop_duplicates(subset=["sentence_ID"])
    log(sentence_level_data["intent"].value_counts())
    log("\nLabel distribution:")
    log(data["label"].value_counts())

    sentences = group_sentences(data)
    classifier = train_model(sentences)
    save_model(classifier)


if __name__ == "__main__":
    main()
