import os
import subprocess


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


EXP006_DIR = os.path.dirname(BASE_DIR)


BUG_REPORT_DIR = os.path.join(
    EXP006_DIR,
    "bug_reports"
)


OUTPUT_DIR = os.path.join(
    EXP006_DIR,
    "bug_patterns"
)


BUILD_SCRIPT = os.path.join(
    BASE_DIR,
    "build_pattern_json.py"
)


def main():

    apis = [
        api
        for api in os.listdir(BUG_REPORT_DIR)
        if os.path.isdir(
            os.path.join(
                BUG_REPORT_DIR,
                api
            )
        )
    ]


    print(
        "Total APIs:",
        len(apis)
    )


    for api in sorted(apis):

        print("="*50)
        print("Processing:", api)


        cmd = [
            "python3",
            BUILD_SCRIPT,
            "--api",
            api,
            "--output",
            OUTPUT_DIR
        ]


        try:

            subprocess.run(
                cmd,
                check=True
            )


        except subprocess.CalledProcessError:

            print(
                "Failed:",
                api
            )


if __name__=="__main__":
    main()
