import os
import csv
import re
import hashlib


BASE_DIR = "results/raw/EXP007/baseline"

COV_DIR = "third_party/FlashFuzz/_cov_result/torch2.2-cov-600s"

OUT_FILE = "results/processed/EXP007/baseline_summary.csv"



def check_fuzz(run_dir):

    log = os.path.join(
        run_dir,
        "fuzz",
        "fuzz-0.log"
    )

    return os.path.exists(log)



def get_crash_info(run_dir):

    artifact_dir = os.path.join(
        run_dir,
        "fuzz",
        "artifacts"
    )

    if not os.path.exists(artifact_dir):
        return 0,0


    crashes=[]

    for f in os.listdir(artifact_dir):

        if f.startswith("crash"):

            path=os.path.join(
                artifact_dir,
                f
            )

            crashes.append(path)


    hashes=set()

    for c in crashes:

        with open(c,"rb") as f:

            h=hashlib.sha256(
                f.read()
            ).hexdigest()

            hashes.add(h)


    return len(crashes),len(hashes)



def get_api_coverage(api):

    txt=os.path.join(
        COV_DIR,
        api,
        "0-600.txt"
    )

    if not os.path.exists(txt):

        return None


    with open(txt) as f:

        data=f.read()


    match=re.search(
        r"(\d+)/(\d+)\s*=\s*([\d.]+)%",
        data
    )


    if match:

        return (
            int(match.group(1)),
            int(match.group(2)),
            float(match.group(3))
        )


    return None



rows=[]


for api in sorted(os.listdir(BASE_DIR)):


    api_dir=os.path.join(
        BASE_DIR,
        api
    )


    if not os.path.isdir(api_dir):
        continue


    if api=="crash_cases":
        continue



    coverage=get_api_coverage(api)


    for run in sorted(os.listdir(api_dir)):


        if not run.startswith("run"):
            continue


        run_dir=os.path.join(
            api_dir,
            run
        )


        crash,total=get_crash_info(
            run_dir
        )


        rows.append({

            "api":api,

            "run":run,

            "fuzz_success":
                check_fuzz(run_dir),

            "covered_lines":
                coverage[0] if coverage else "",

            "total_lines":
                coverage[1] if coverage else "",

            "line_coverage":
                coverage[2] if coverage else "",

            "crash_count":
                crash,

            "unique_crash_count":
                total

        })



os.makedirs(
    os.path.dirname(OUT_FILE),
    exist_ok=True
)


with open(
    OUT_FILE,
    "w",
    newline=""
) as f:


    writer=csv.DictWriter(
        f,
        fieldnames=rows[0].keys()
    )

    writer.writeheader()

    writer.writerows(rows)



print(
    "Saved:",
    OUT_FILE
)
