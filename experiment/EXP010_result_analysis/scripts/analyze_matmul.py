import csv


summary_file = "data/torch.matmul_summary.csv"

rows = []

with open(summary_file, "r") as f:
    reader = csv.DictReader(f)

    for row in reader:
        rows.append(row)


baseline = 0

for row in rows:
    if row["method"] == "baseline":
        baseline = float(row["coverage"])


print("=" * 60)
print("Torch.matmul Coverage Analysis")
print("=" * 60)


for row in rows:

    method = row["method"]
    coverage = float(row["coverage"])

    improvement = (
        (coverage - baseline)
        / baseline
        * 100
    )

    print(
        f"{method:<20}"
        f"{coverage:.2f}%   "
        f"Improvement: {improvement:.2f}%"
    )
