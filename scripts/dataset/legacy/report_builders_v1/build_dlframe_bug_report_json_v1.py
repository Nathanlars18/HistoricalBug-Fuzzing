import os
import csv
import json
import re


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


PROJECT_DIR = os.path.join(
    BASE_DIR,
    ".."
)


CSV_FILE = os.path.join(
    PROJECT_DIR,
    "analysis/selected_bug_review_final.csv"
)


RAW_DIR = os.path.join(
    PROJECT_DIR,
    "raw_reports"
)


EXP006_DIR = os.path.expanduser(
    "~/FlashFuzz/experiment/EXP006_historical_bug_pattern_dataset"
)

OUT_DIR = os.path.join(
    EXP006_DIR,
    "bug_reports"
)

os.makedirs(
    OUT_DIR,
    exist_ok=True
)



def extract_title(text):

    match = re.search(
        r"\[Title\]\s*(.*)",
        text
    )

    if match:
        return match.group(1).strip()

    return ""


def clean_bug(text):

    text=text.replace(
        "<!-- A clear and concise description of what the bug is. -->",
        ""
    )

    return text.strip()

def normalize_api_name(api):

    name = api.split(".")[-1]

    # remove markdown style markers if any
    name = name.replace("*", "")

    # __getitem__ -> getitem
    name = re.sub(
        r"__([a-zA-Z0-9_]+)__",
        r"\1",
        name
    )

    return name


def normalize_api_dir(api):

    name = api

    # remove markdown style markers
    name = name.replace("*", "")

    # normalize python magic methods:
    # __getitem__ -> getitem
    name = re.sub(
        r"__([a-zA-Z0-9_]+)__",
        r"\1",
        name
    )

    return name

def extract_bug_section(text):

    start = text.find("## 🐛 Bug")

    end = text.find("## To Reproduce")


    if start != -1:

        if end != -1:
            return text[start:end].strip()

        return text[start:].strip()


    return ""



with open(
    CSV_FILE,
    newline="",
    encoding="utf-8-sig"
) as f:

    reader = csv.DictReader(f)


    count = 0


    for row in reader:


        if row["human_include"] != "Yes":
            continue


        bug_id = row["bug_id"]


        raw_file = os.path.join(
            RAW_DIR,
            f"{bug_id}_summary_with_code.txt"
        )


        if not os.path.exists(raw_file):

            print(
                "Missing:",
                raw_file
            )

            continue



        with open(
            raw_file,
            encoding="utf-8"
        ) as rf:

            raw_text = rf.read()



        report = {

            "metadata":{
                "bug_id":bug_id,
                "title":extract_title(raw_text)
            },


            "source_information":{
                "repository":"PyTorch",
                "source_type":"GitHub Issue"
            },


            "api_information":{
                "primary_api":
                    row["target_api"],

                "affected_apis":[]
            },


            "bug_description":
                clean_bug(
                    extract_bug_section(raw_text)
                ),



            "trigger_conditions":{
                "category":
                    row["human_category"],

                "pattern":
                    row["human_pattern"],

                "condition":
                    row["human_trigger"],

                "operation_context":
                    row["trigger_condition"]
            },



            "failure_behavior":{
                "type":
                    row["oracle_type"],

                "description":
                    row["trigger_condition"],

                "oracle":
                    row["oracle_type"]
            },


            "root_cause_information":{
                "layer":"",
                "description":""
            },


            "fix_information":{
                "fixed":"unknown",
                "fix_description":"",
                "commit":""
            },


            "verification_information":{
                "status":
                    "human_verified",

                "confidence":
                    row["confidence"]
            },


            "raw_content_reference":
                f"raw_reports/{bug_id}_summary_with_code.txt"
        }



        api_name = row["target_api"]

        normalized_dir = normalize_api_dir(api_name)

        api_dir = os.path.join(
            OUT_DIR,
            normalized_dir
        )

        os.makedirs(
            api_dir,
            exist_ok=True
        )


        safe_api_name = normalize_api_name(api_name)


        existing_ids = []


        for file in os.listdir(api_dir):

            match = re.search(
                rf"{safe_api_name}_bug_(\d+).json",
                file
            )

            if match:
                existing_ids.append(
                    int(match.group(1))
                )


        if existing_ids:
            next_id = max(existing_ids)+1
        else:
            next_id = 1



        output = os.path.join(
            api_dir,
            f"{safe_api_name}_bug_{next_id:03d}.json"
        )


        if os.path.exists(output):

            print(
                "Skip existing:",
                output
            )

            continue

        with open(
            output,
            "w",
            encoding="utf-8"
        ) as out:

            json.dump(
                report,
                out,
                indent=4,
                ensure_ascii=False
            )


        count += 1



print(
    "Generated reports:",
    count
)
