import argparse
import subprocess
import os
import shutil

ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "../../.."
    )
)


FLASHFUZZ = os.path.join(
    ROOT,
    "third_party/FlashFuzz"
)


RESULT_DIR = os.path.join(
    ROOT,
    "results/raw/EXP007/baseline"
)

def read_api_list(path):

    with open(path) as f:
        return [
            line.strip()
            for line in f
            if line.strip()
        ]


def run(cmd, cwd):

    print("="*50)
    print(cmd)

    subprocess.run(
        cmd,
        cwd=cwd,
        shell=True,
        check=True
    )

def copy_results(src, dst):

    if os.path.exists(dst):
        shutil.rmtree(dst)

    shutil.copytree(
        src,
        dst
    )

    print(
        f"Copied {src} -> {dst}"
    )


def main():

    parser = argparse.ArgumentParser()


    parser.add_argument(
        "--api"
    )


    parser.add_argument(
        "--api-file"
    )


    parser.add_argument(
        "--repeat",
        type=int,
        default=1
    )

    parser.add_argument(
        "--start-run",
        type=int,
        default=1
    )

    parser.add_argument(
        "--itv",
        type=int,
        default=None
    )


    parser.add_argument(
        "--time",
        type=int,
        default=30
    )


    args = parser.parse_args()


    if args.api_file:

        apis = read_api_list(
            args.api_file
        )

    else:

        apis = [
            args.api
        ]


    for api in apis:


        for run_id in range(
            args.start_run,
            args.start_run + args.repeat
        ):


            print(
                "=" * 60
            )

            print(
                f"Running {api} repeat {run_id}"
            )


            result = os.path.join(
                RESULT_DIR,
                api,
                f"run_{run_id}"
            )


            os.makedirs(
                result,
                exist_ok=True
            )


            ################################
            # Fuzz
            ################################

            cmd = f"""
python3 run.py \
--dll torch \
--version 2.2 \
--mode fuzz \
--apis {api} \
--time_budget {args.time}
"""


            run(
                cmd,
                FLASHFUZZ
            )


            src = os.path.join(
                FLASHFUZZ,
                "_fuzz_result",
                f"torch2.2-fuzz-{args.time}s",
                api
            )


            dst = os.path.join(
                result,
                "fuzz"
            )


            copy_results(
                src,
                dst
            )


            ################################
            # Coverage
            ################################

            cmd = f"""
python3 run.py \
--dll torch \
--version 2.2 \
--mode cov \
--apis {api} \
--time_budget {args.time} \
--itv {args.itv if args.itv else args.time}
"""


            run(
                cmd,
                FLASHFUZZ
            )


            src = os.path.join(
                FLASHFUZZ,
                "_cov_result",
                f"torch2.2-cov-{args.time}s",
                api
            )


            dst = os.path.join(
                result,
                "coverage"
            )


            copy_results(
                src,
                dst
            )


            print(
                f"Finished {api} repeat {run_id}"
            )


if __name__=="__main__":
    main()
