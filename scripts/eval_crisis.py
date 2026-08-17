import csv
import sys
from pathlib import Path

# Add server directory to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "server"))
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from services.crisis_rules import evaluate_deterministic_crisis

file_path = Path(__file__).resolve().parent.parent / "tests" / "data" / "crisis_test_utterances.csv"

total = 0
tp = fp = tn = fn = 0

with open(file_path, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    for row in reader:
        total += 1
        text = row['text']
        cat = row['category']
        severity = int(row['severity'])
        
        is_actual_crisis = (severity >= 3) and (cat not in ['idiom_non_crisis', 'negation_past_academic'])
        
        res = evaluate_deterministic_crisis(text)
        pred_crisis = res['is_crisis']
        
        if pred_crisis and is_actual_crisis:
            tp += 1
        elif pred_crisis and not is_actual_crisis:
            fp += 1
        elif not pred_crisis and not is_actual_crisis:
            tn += 1
        elif not pred_crisis and is_actual_crisis:
            fn += 1

acc = (tp + tn) / total if total else 0
prec = tp / (tp + fp) if (tp + fp) else 0
rec = tp / (tp + fn) if (tp + fn) else 0
f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
fnr = fn / (tp + fn) if (tp + fn) else 0
fpr = fp / (fp + tn) if (fp + tn) else 0

print(f"Total Test Cases:     {total}")
print(f"TP: {tp}, FP: {fp}, TN: {tn}, FN: {fn}")
print(f"Accuracy:             {acc*100:.2f}%")
print(f"Precision:            {prec*100:.2f}%")
print(f"Recall (Sensitivity): {rec*100:.2f}%")
print(f"F1-Score:             {f1*100:.2f}%")
print(f"False Neg Rate:       {fnr*100:.2f}%")
print(f"False Pos Rate:       {fpr*100:.2f}%")
