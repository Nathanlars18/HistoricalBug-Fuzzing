import os
import re
import json
import argparse


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


PROJECT_DIR = os.path.abspath(
    os.path.join(BASE_DIR, "../../..")
)


ISSUE_ROOT = os.path.join(
    PROJECT_DIR,
    "dataset",
    "interim",
    "github_issue_collection"
)


EXP006_DIR = os.path.join(
    PROJECT_DIR,
    "experiment",
    "EXP006_historical_bug_pattern_dataset"
)


OUTPUT_ROOT = os.path.join(
    EXP006_DIR,
    "bug_reports"
)


def read_text(path):
    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return f.read()



def extract_between(text, start, end=None):

    pos = text.find(start)

    if pos == -1:
        return ""

    pos += len(start)

    if end:

        end_pos = text.find(
            end,
            pos
        )

        if end_pos != -1:
            return text[pos:end_pos].strip()

    return text[pos:].strip()



def extract_title(text):

    match = re.search(
        r"Title:\s*\n?(.*)",
        text
    )

    if match:
        return match.group(1).strip()

    return ""



def extract_issue_id(text):

    match = re.search(
        r"(?:Issue ID|Issue):\s*#?(\d+)",
        text
    )

    if match:
        return match.group(1)

    return ""



def get_next_id(output_dir, prefix):

    os.makedirs(
        output_dir,
        exist_ok=True
    )

    ids = []

    for f in os.listdir(output_dir):

        match = re.search(
            rf"{prefix}_bug_(\d+)\.json",
            f
        )

        if match:
            ids.append(
                int(match.group(1))
            )

    if ids:
        return max(ids) + 1

    return 1



def build_report(issue_file, api):

    text = read_text(
        issue_file
    )

    issue_id = extract_issue_id(
        text
    )


    return {

        "metadata": {

            "bug_id":
                f"pytorch_{issue_id}",

            "title":
                extract_title(text),

            "date":
                ""

        },


        "source_information": {

            "repository":
                "pytorch/pytorch",

            "issue_id":
                issue_id,

            "source_type":
                "GitHub Issue",

            "issue_url":
                "",

            "pr_id":
                "",

            "commit_id":
                ""

        },


        "api_information": {

            "primary_api":
                api,

            "affected_apis":
                [],

            "operator":
                "",

            "module":
                ""

        },


        "bug_description":
            extract_between(
                text,
                "Description:"
            ),


        "trigger_conditions": {

            "shape": [],

            "dtype": [],

            "device": [],

            "backend": [],

            "layout": [],

            "memory": [],

            "state": [],

            "operation_context":
                ""

        },


        "failure_behavior": {

            "type":
                "",

            "description":
                "",

            "oracle":
                ""

        },


        "root_cause_information": {

            "layer":
                "",

            "description":
                ""

        },


        "fix_information": {

            "fixed":
                False,

            "fix_description":
                "",

            "commit":
                ""

        },


        "verification_information": {

            "status":
                "",

            "confidence":
                ""

        },


        "raw_content_reference":
            os.path.relpath(
                issue_file,
                PROJECT_DIR
            )

    }



def process_api(api):

    input_dir = os.path.join(
        ISSUE_ROOT,
        api
    )

    output_dir = os.path.join(
        OUTPUT_ROOT,
        api
    )


    prefix = api.split(".")[-1]


    next_id = get_next_id(
        output_dir,
        prefix
    )


    count = 0


    for file in sorted(
        os.listdir(input_dir)
    ):

        if not file.endswith(".txt"):
            continue


        path = os.path.join(
            input_dir,
            file
        )


        report = build_report(
            path,
            api
        )


        output = os.path.join(
            output_dir,
            f"{prefix}_bug_{next_id:03d}.json"
        )


        with open(
            output,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                report,
                f,
                indent=4,
                ensure_ascii=False
            )


        print(
            "Generated:",
            output
        )


        next_id += 1
        count += 1


    print(
        api,
        "total:",
        count
    )



if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--api"
    )

    parser.add_argument(
        "--all",
        action="store_true"
    )


    args = parser.parse_args()


    if args.api:

        process_api(
            args.api
        )

    elif args.all:

        for api in os.listdir(
            ISSUE_ROOT
        ):

            if os.path.isdir(
                os.path.join(
                    ISSUE_ROOT,
                    api
                )
            ):

                process_api(api)

