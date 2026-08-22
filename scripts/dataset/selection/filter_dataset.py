import os
import re
import csv


REPORT_DIR = "../raw_reports"
CODE_DIR = "../reproduction_code"

OUTPUT = "../analysis/bug_selection_auto.csv"


def extract_title(content):
    match = re.search(r"\[Title\](.*)", content)

    if match:
        return match.group(1).strip()

    return ""


def detect_api(content):

    apis = re.findall(
        r"torch(?:\.[a-zA-Z_0-9]+)+",
        content
    )

    return list(set(apis))


def detect_failure(content):

    result=[]

    keywords = {
        "Crash": [
            "crash",
            "segfault",
            "SIGSEGV",
            "SIGFPE"
        ],

        "Exception":[
            "RuntimeError",
            "ValueError",
            "AssertionError"
        ],

        "Incorrect Output":[
            "wrong",
            "incorrect",
            "unexpected",
            "different result"
        ]
    }


    for k,v in keywords.items():

        for word in v:
            if word.lower() in content.lower():
                result.append(k)
                break

    return ",".join(result)



rows=[]


for file in os.listdir(REPORT_DIR):

    if not file.endswith(".txt"):
        continue


    bug_id=file.split("_")[0]


    report_path=os.path.join(
        REPORT_DIR,
        file
    )


    with open(
        report_path,
        encoding="utf-8"
    ) as f:

        content=f.read()


    code_exists=os.path.exists(
        os.path.join(
            CODE_DIR,
            bug_id+".py"
        )
    )


    rows.append({

        "bug_id":bug_id,

        "title":extract_title(content),

        "api_candidates":
            ",".join(
                detect_api(content)
            ),

        "has_reproduction_code":
            "Yes" if code_exists else "No",

        "failure_type":
            detect_failure(content),

        "pattern_extractability":"",
        
        "include":"",
        
        "reason":""

    })



with open(
    OUTPUT,
    "w",
    newline="",
    encoding="utf-8"
) as f:


    writer=csv.DictWriter(
        f,
        fieldnames=rows[0].keys()
    )

    writer.writeheader()

    writer.writerows(rows)



print(
    "Generated:",
    OUTPUT
)
