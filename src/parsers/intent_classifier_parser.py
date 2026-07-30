"""Implementation of a parser that uses a trained model only for intent classification."""

from pathlib import Path
import joblib
from typing import Optional

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from .rule_based_parser import RuleBasedParser


class IntentClassifierParser(RuleBasedParser):
    """Parser that uses a learned model for intent classification.

    This parser predicts the command intent with a trained classifier, but
    inherits the rule-based reference parsing methods from RuleBasedParser.
    """

    def __init__(
        self,
        intent_model: Optional[LogisticRegression] = None,
        vectorizer: Optional[TfidfVectorizer] = None
    ) -> None:
        """Use provided model objects or load the saved intent classifier."""
        
        super().__init__()
        if vectorizer is None or intent_model is None:
            model_dir = Path(__file__).resolve().parents[2] / "models"
            self.vectorizer = joblib.load(model_dir / "intent_vectorizer.joblib")
            self.intent_model = joblib.load(model_dir / "intent_classifier.joblib")
        else:
            self.vectorizer = vectorizer
            self.intent_model = intent_model

            
    def parse_intent(self, text: str) -> str:
        """Predict the command intent with the learned intent classifier."""
        
        normalized = self.normalize_text(text)
        X = self.vectorizer.transform([normalized])
        return str(self.intent_model.predict(X)[0])
