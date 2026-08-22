import os
import json
import csv


INPUT_DIR = "../analysis/llm_raw_response"
OUTPUT_FILE = "../analysis/bug_selection_llm.csv"


fields = [
    "bug_id",
    "target_api",
    "bug_category",
    "trigger_condition",
    "oracle_type",
    "pattern_extractability",
    "knowledge_generation_feasibility",
    "include",
    "confidence",
    "reason"
]


rows = []


for filename in os.listdir(INPUT_DIR):

    if not filename.endswith(".json"):
        continue

    bug_id = filename.replace(".json","")

    path = os.path.join(
        INPUT_DIR,
        filename
    )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:

        data = json.load(f)


    data["bug_id"] = bug_id

    rows.append(data)



with open(
    OUTPUT_FILE,
    "w",
    newline="",
    encoding="utf-8"
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=fields
    )

    writer.writeheader()

    for row in rows:

        clean_row = {
            field: row.get(field, "")
            for field in fields
        }

        writer.writerow(clean_row)



print(
    "Generated:",
    OUTPUT_FILE
)

print(
    "Total:",
    len(rows)
)
