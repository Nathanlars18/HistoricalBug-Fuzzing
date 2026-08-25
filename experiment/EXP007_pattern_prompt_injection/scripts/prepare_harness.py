import os
import shutil
import argparse


PROJECT_ROOT = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "../../.."
    )
)


FLASHFUZZ_DIR = os.path.join(
    PROJECT_ROOT,
    "third_party/FlashFuzz"
)

def read_api_list(path):

    with open(path) as f:
        return [
            line.strip()
            for line in f
            if line.strip()
        ]


def copy_harness(api, mode):

    src_dir = os.path.join(
        PROJECT_ROOT,
        "experiment",
        "EXP007_pattern_prompt_injection",
        "harnesses",
        mode,
        api
    )


    dst_dir = os.path.join(
        FLASHFUZZ_DIR,
        "testharness",
        "torch_cpu",
        api
    )


    if not os.path.exists(src_dir):
        raise FileNotFoundError(
            f"Missing harness dir: {src_dir}"
        )


    os.makedirs(
        dst_dir,
        exist_ok=True
    )


    for file in os.listdir(src_dir):

        src = os.path.join(
            src_dir,
            file
        )

        dst = os.path.join(
            dst_dir,
            file
        )

        shutil.copy2(
            src,
            dst
        )


    print(
        f"Copied directory:\n{src_dir}\n ->\n{dst_dir}"
    )


if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--api"
    )

    parser.add_argument(
        "--api-file"
    )

    parser.add_argument(
        "--mode",
        default="baseline"
    )


    args = parser.parse_args()


    if args.api_file:

        apis = read_api_list(args.api_file)

    else:

        apis = [args.api]


    for api in apis:

        copy_harness(
            api,
            args.mode
        )
