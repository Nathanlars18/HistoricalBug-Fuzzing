import os
import subprocess
import csv
import re


BASELINE_DIR = "results/raw/EXP007/baseline"

FLASHFUZZ_DIR = "third_party/FlashFuzz"

OUTPUT = "results/processed/EXP007/baseline_coverage_summary.csv"

IMAGE = "ncsuswat/flashfuzz:torch2.2-cov"

BINARY = "/root/pytorch/build-fuzz/lib/libtorch_cpu.so"

def parse_coverage(txt_file):

    if not os.path.exists(txt_file):
        print("Missing coverage file:", txt_file)
        return None, None, None


    with open(txt_file, "r") as f:
        text = f.read()


    import re


    covered_match = re.search(
        r"Covered branches:\s*(\d+)",
        text
    )

    total_match = re.search(
        r"Total branches:\s*(\d+)",
        text
    )

    coverage_match = re.search(
        r"Branch coverage:\s*([\d.]+)%",
        text
    )


    if not covered_match or not total_match or not coverage_match:
        print("Cannot parse coverage:")
        print(text[:500])
        return None, None, None


    covered = int(
        covered_match.group(1)
    )

    total = int(
        total_match.group(1)
    )

    coverage = float(
        coverage_match.group(1)
    )


    return covered, total, coverage


def analyze_one(api, run):


    coverage_dir = os.path.join(
        BASELINE_DIR,
        api,
        run,
        "coverage"
    )


    if not os.path.exists(coverage_dir):
        return None


    coverage_data_dir = os.path.join(
        coverage_dir,
        "coverage_data"
    )


    normal_dir = os.path.join(
        coverage_data_dir,
        "0-600"
    )


    work_dir = os.path.join(
        coverage_data_dir,
        ".work",
        "run_0-600"
    )


    if os.path.exists(normal_dir) and \
       len(os.listdir(normal_dir)) > 0:

        profraw_dir = normal_dir

    elif os.path.exists(work_dir):

        profraw_dir = work_dir

    else:

        print(
            f"No profraw found: {coverage_dir}"
        )

        return {
            "covered_lines":0,
            "total_lines":30094,
            "line_coverage":0
        }


    if not os.path.exists(profraw_dir):
        return None



    print(
        "Processing:",
        api,
        run
    )


    # 生成profdata

    profdata = os.path.join(
        profraw_dir,
        "merged.profdata"
    )


    cmd_merge = [
        "docker",
        "run",
        "--rm",

        "-v",
        f"{os.path.abspath(profraw_dir)}:/root/fuzz/data",

        "-v",
        f"{os.path.abspath(FLASHFUZZ_DIR)}:/root/fuzz",


        IMAGE,

        "python3",
        "/root/fuzz/scripts/merge_profraw.py",

        "--dll",
        "torch",

        "--dir",
        "/root/fuzz/data",

        "--out",
        "/root/fuzz/data/merged.profdata"
    ]

    subprocess.run(
        cmd_merge,
        check=True
    )


    # 输出txt

    output_txt = os.path.join(
        profraw_dir,
        "coverage_result.txt"
    )


    cmd_cov = [
        "docker",
        "run",
        "--rm",

        "-v",
        f"{os.path.abspath(profraw_dir)}:/root/fuzz/data",

        "-v",
        f"{os.path.abspath(FLASHFUZZ_DIR)}:/root/fuzz",

        IMAGE,

        "python3",
        "/root/fuzz/scripts/get_coverage_results.py",

        "--binary",
        "/root/pytorch/build-fuzz/lib/libtorch_cpu.so",

        "--dll",
        "torch",

        "--require",
        "aten/src/ATen/native",

        "--coverage_file",
        "/root/fuzz/data/merged.profdata",

        "--out",
        "/root/fuzz/data/coverage_result.txt"
    ]

    subprocess.run(
        cmd_cov,
        check=True
    )


    return parse_coverage(output_txt)




def main():

    results=[]


    for api in sorted(os.listdir(BASELINE_DIR)):

        api_dir=os.path.join(
            BASELINE_DIR,
            api
        )


        if not os.path.isdir(api_dir):
            continue


        for run in sorted(os.listdir(api_dir)):


            if not run.startswith("run_"):
                continue


            result=analyze_one(
                api,
                run
            )


            if result:

                covered,total,cov=result

                results.append(
                    {
                        "api":api,
                        "run":run,
                        "covered_branches":covered,
                        "total_branches":total,
                        "branch_coverage":cov
                    }
                )



    os.makedirs(
        os.path.dirname(OUTPUT),
        exist_ok=True
    )


    with open(
        OUTPUT,
        "w",
        newline=""
    ) as f:


        writer=csv.DictWriter(
            f,
            fieldnames=[
                "api",
                "run",
                "covered_branches",
                "total_branches",
                "branch_coverage"
            ]
        )


        writer.writeheader()

        writer.writerows(results)


    print(
        "Saved:",
        OUTPUT
    )



if __name__=="__main__":
    main()
