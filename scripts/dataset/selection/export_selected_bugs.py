import os
import json
import csv


INPUT_DIR = "../analysis/llm_raw_response"

OUTPUT_FILE = "../analysis/selected_bug_candidates.csv"


rows = []


for file in os.listdir(INPUT_DIR):

    if not file.endswith(".json"):
        continue


    path = os.path.join(INPUT_DIR, file)


    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)


    if data.get("include") != "Yes":
        continue


    rows.append({

        "bug_id":
            data.get("bug_id",""),

        "target_api":
            data.get("target_api",""),

        "bug_category":
            data.get("bug_category",""),

        "trigger_condition":
            data.get("trigger_condition",""),

        "oracle_type":
            data.get("oracle_type",""),

        "pattern_extractability":
            data.get("pattern_extractability",""),

        "knowledge_generation_feasibility":
            data.get("knowledge_generation_feasibility",""),

        "confidence":
            data.get("confidence",""),

        "reason":
            data.get("reason","")

    })


rows.sort(
    key=lambda x:int(x["bug_id"])
)


with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8",
    newline=""
) as f:

    writer = csv.DictWriter(
        f,
        fieldnames=rows[0].keys()
    )

    writer.writeheader()

    writer.writerows(rows)


print(
    "Generated:",
    OUTPUT_FILE
)

print(
    "Selected:",
    len(rows)
)
