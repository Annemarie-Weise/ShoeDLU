"""Train and evaluate the intent classifier for shoe-world commands.

The script loads and cleans labeled command data, converts commands into
TF-IDF features, trains a logistic-regression classifier, evaluates it on
a stratified test split, and saves the trained vectorizer and classifier.

Run from the project root with:
python -m src.parsers.training_stage2.train_intent_classifier
"""

import sys
from pathlib import Path
from datetime import datetime

import joblib
import pandas as pd
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix
)
from sklearn.model_selection import train_test_split

PROJECT_ROOT = Path(__file__).resolve().parents[3]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain_rules_and_constants import VALID_INTENTS



DATA_DIR = PROJECT_ROOT / "data" / "model_training_data"
MODEL_DIR = PROJECT_ROOT / "models"
LOG_DIR = PROJECT_ROOT / "evaluation_results" / "model_training_logs"
DATA_PATH = DATA_DIR / "intent_training_dataset.csv"

timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
LOG_PATH = LOG_DIR / f"intent_classifier_training_log_{timestamp}.log"



def log(message: object = "") -> None:
    """Print a message and append it to the training log file."""
    
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    message = str(message)
    print(message)
    with open(LOG_PATH, "a", encoding="utf-8") as file:
        file.write(message + "\n")

    

def load_dataset() -> pd.DataFrame:
    """Load and clean the intent-classification dataset."""

    data = pd.read_csv(DATA_PATH, sep=";")

    # Remove rows with missing labels or commands and normalize whitespace
    data = data.dropna(subset=["command", "intent"])
    data["command"] = data["command"].astype(str).str.strip()
    data["intent"] = data["intent"].astype(str).str.strip()

    # Keep only intents supported by the shoe-world system
    data = data[data["intent"].isin(VALID_INTENTS)]

    # Remove exact duplicate command-intent pairs
    data = data.drop_duplicates(subset=["command", "intent"])
    return data



def evaluate_predictions(
    title: str,
    gold_labels: pd.Series,
    predicted_labels: np.ndarray,
    classifier: LogisticRegression,
) -> None:
    """Log accuracy, a classification report, and a confusion matrix."""

    log("\n" + "#" * 100 + f"\n{title}\n" + "#" * 100)
    log(f"Accuracy: {accuracy_score(gold_labels, predicted_labels):.4f}")
    log("\nClassification report:")
    log(classification_report(gold_labels, predicted_labels))
    log("\nConfusion matrix labels:")
    log(classifier.classes_)
    log("\nConfusion matrix:")
    log(confusion_matrix(gold_labels, predicted_labels, labels=classifier.classes_))

    

def train_model(data: pd.DataFrame):
    """Train the intent classifier and evaluate it on a random test split."""

    commands = data["command"]
    labels = data["intent"]
    
    command_train, command_test, label_for_train, label_for_test = train_test_split(
        commands,
        labels,
        test_size=0.25,  # Use 25% of the data for testing
        random_state=404,  # Fixed seed for reproducible result
        stratify=labels  # Keep the intent distribution similar in train and test data
    )

    # Convert text commands into numeric features
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1, 2),  # Use unigrams and bigrams, e.g. "clean" and "pick up"
        min_df=1  # Keep terms even if they appear only once in training data
    )

    # Learn the vocabulary from training data and convert training commands to vectors
    command_train_vectorized = vectorizer.fit_transform(command_train)
    # Convert test commands using only the vocabulary learned from training data
    command_test_vectorized = vectorizer.transform(command_test)

    classifier = LogisticRegression(
        max_iter=1000,
        solver="lbfgs",  # General-purpose optimizer for multiclass classification
        class_weight="balanced"  # Give smaller classes more weight during training
    )

    # Train the classifier: numeric command features -> correct intent labels
    classifier.fit(command_train_vectorized, label_for_train)

    # Predict intent labels for the held-out test commands
    y_pred = classifier.predict(command_test_vectorized)

    log("#" * 100 + "\nIntent Classification Results\n" + "#" * 100)
    log(f"Training examples: {len(command_train)}")
    log(f"Test examples:     {len(command_test)}\n")

    evaluate_predictions(
        title="Random Test Split Evaluation",
        gold_labels=label_for_test,
        predicted_labels=y_pred,
        classifier=classifier
    )
    return vectorizer, classifier


    
def save_model(
    vectorizer: TfidfVectorizer,
    classifier: LogisticRegression,
) -> None:
    """Save the trained vectorizer and classifier to the model directory."""
    
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    vectorizer_path = MODEL_DIR / "intent_vectorizer.joblib"
    classifier_path = MODEL_DIR / "intent_classifier.joblib"
    joblib.dump(vectorizer, vectorizer_path)
    joblib.dump(classifier, classifier_path)



def main() -> None:
    """Run the complete intent classification training and evaluation pipeline."""
    
    data = load_dataset()
    
    log("#" * 100 + "\nLoaded dataset\n" + "#" * 100)
    log(f"Total examples after cleanup: {len(data)}\n\n")
    log("Class distribution:")
    log(data["intent"].value_counts())

    vectorizer, classifier = train_model(data)
    save_model(vectorizer, classifier)


if __name__ == "__main__":
    main()
