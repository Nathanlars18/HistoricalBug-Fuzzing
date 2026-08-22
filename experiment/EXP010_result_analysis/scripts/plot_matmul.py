import csv
import matplotlib.pyplot as plt


input_file = "data/torch.matmul_growth.csv"

time=[]
baseline=[]
single=[]
multi=[]
reasoning=[]


with open(input_file) as f:
    reader = csv.DictReader(f)

    for row in reader:
        time.append(int(row["time"]))
        baseline.append(float(row["baseline"]))
        single.append(float(row["single_pattern"]))
        multi.append(float(row["multi_pattern"]))
        reasoning.append(float(row["reasoning_pattern"]))


plt.figure(figsize=(8,5))

plt.plot(time, baseline, label="Baseline")
plt.plot(time, single, label="Single Pattern")
plt.plot(time, multi, label="Multi Pattern")
plt.plot(time, reasoning, label="Reasoning Pattern")


plt.xlabel("Time (seconds)")
plt.ylabel("Branch Coverage (%)")

plt.title(
    "torch.matmul Coverage Growth"
)

plt.legend()

plt.grid(True)

plt.savefig(
    "figures/torch.matmul_coverage_curve.png",
    dpi=300,
    bbox_inches="tight"
)

print(
    "Saved figures/torch.matmul_coverage_curve.png"
)
