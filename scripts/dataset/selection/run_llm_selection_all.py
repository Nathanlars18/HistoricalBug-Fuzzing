import os
import subprocess


BUG_DIR="../raw_reports"

OUTPUT_DIR="../analysis/llm_raw_response"


bugs=[]


for f in os.listdir(BUG_DIR):

    if f.endswith("_summary_with_code.txt"):

        bug_id=f.split("_")[0]

        bugs.append(bug_id)



bugs.sort()


print(
    "Total bugs:",
    len(bugs)
)



for bug_id in bugs:


    output_file = (
        OUTPUT_DIR
        +
        "/"
        +
        bug_id
        +
        ".json"
    )


    if os.path.exists(output_file):

        print(
            "Skip existing:",
            bug_id
        )

        continue



    print("\n==========")
    print(
        "Processing",
        bug_id
    )
    print("==========")


    cmd=[
        "python3",
        "llm_bug_selector.py",
        "--api_key",
        os.environ["DEEPSEEK_API_KEY"],
        "--model",
        "deepseek-v4-pro",
        "--bug_id",
        bug_id
    ]


    result=subprocess.run(
        cmd,
        capture_output=True,
        text=True
    )


    print(result.stdout)


    if result.returncode !=0:

        print(
            "[FAILED]",
            bug_id
        )

        print(
            result.stderr
        )
