# Category model card

## Intended use

Suggest a main category from an English product name. Review predictions before
changing a real catalog. This is a classification exercise, not a pricing model.

## Data and evaluation

The target is the category segment before `|`; the only feature is product name.
IDs, prices, reviews, and category labels are never model features. Blank rows,
duplicate IDs, and normalized identical titles are removed before splitting.
Categories with fewer than five distinct titles are reported and excluded.

A seeded per-category split reserves about 20% each for validation and testing.
The 100-row demo has 62 training, 19 validation, and 19 test rows across two
categories. Similar product families can still cross splits; use family-level
or temporal separation before deployment decisions.

TF-IDF unigrams/bigrams feed class-balanced logistic regression. Validation
macro-F1 chooses C=0.5 or C=2.0. The selected training-only model is tested without
refitting. The saved artifact is exactly the evaluated model. Reports include a
majority-class baseline, per-class precision/recall/F1, confusion matrix, errors,
split IDs, seed, software versions, and a data fingerprint.

Do not repeatedly tune against the test set and call it unseen evaluation.
Use validation during development and reserve fresh data for a later assessment.

## Artifact and inference

`model.json` stores vocabulary, IDF, coefficients, intercepts, class names, and
metadata. It contains no executable pickle. Inference uses the same TF-IDF
settings and sigmoid/softmax equations. Empty names are rejected and completely
unknown vocabulary causes abstention. Familiar words can still belong to an
unseen category. Probabilities are not calibrated confidence.

## Interpreting the demo

See `evaluation/demo/model_evaluation.json`. The sample is the first 100 rows
from the existing project sample, not a representative benchmark. A perfect
score on 19 test items is not proof of 100% real-world accuracy. Related product
variants and easy separation between two categories can inflate the result.

## Updating and rollback

Train into a new directory, review evaluation and errors, then point `MODEL_PATH`
to the reviewed model. Keep the previous directory for rollback. Individual JSON
writes are atomic, but the model and report are separate files: compare their
`model_id`. Do not run concurrent trainers into the same directory.
