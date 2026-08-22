import os
import subprocess


BUG_REPORT_DIR = "bug_reports"

OUTPUT_DIR = "bug_patterns"


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


    print("Total APIs:", len(apis))


    for api in sorted(apis):

        print("="*50)

        print("Processing:", api)


        cmd = [
            "python3",
            "scripts/build_pattern_json.py",
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
