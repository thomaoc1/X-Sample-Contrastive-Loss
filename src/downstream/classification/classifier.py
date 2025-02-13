import argparse
import os

import torch
import pickle
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.preprocessing import StandardScaler


class EmbeddingsClassifier:
    def __init__(self, pretrained_path: str | None = None):
        self._scaler = StandardScaler()
        if not pretrained_path:
            self._classifier = LogisticRegression(max_iter=1000)
        else:
            pass

    def train_classifier(self, X, y, save_path: str | None):
        # Normalise
        X_norm = self._scaler.fit_transform(X)
        self._classifier.fit(X_norm, y)

        if save_path:
            with open(save_path, 'wb') as f:
                pickle.dump(self._classifier, f)

    def evaluate(self, X, y):
        X_norm = self._scaler.fit_transform(X)
        predictions = self._classifier.predict(X_norm)
        return accuracy_score(y, predictions)


def parse_args():
    parser = argparse.ArgumentParser(description="Train and evaluate a classifier on embeddings.")
    parser.add_argument('data_path', type=str, help='Path to the training/test dataset (encoded features) which must contain (train/test).pt')
    parser.add_argument('--save_path', type=str, help='Path to save the trained classifier')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    train_set = torch.load(os.path.join(args.data_path, 'train.pt'), weights_only=False)
    test_set = torch.load(os.path.join(args.data_path, 'test.pt'), weights_only=False)

    train_features = train_set['encodings'].numpy()
    train_labels = train_set['labels'].numpy()
    test_features = test_set['encodings'].numpy()
    test_labels = test_set['labels'].numpy()

    model = EmbeddingsClassifier()
    model.train_classifier(
        train_features,
        train_labels,
        save_path=args.save_path,
    )

    test_accuracy = model.evaluate(test_features, test_labels)
    print(f'Test Accuracy: {test_accuracy * 100:.2f}%')
