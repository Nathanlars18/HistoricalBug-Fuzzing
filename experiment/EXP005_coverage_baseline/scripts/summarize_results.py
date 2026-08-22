import os
import re


RESULT_DIR="results"


print("API\t0-60\t540-600")


for api in sorted(os.listdir(RESULT_DIR)):

    api_dir=os.path.join(
        RESULT_DIR,
        api
    )

    if not os.path.isdir(api_dir):
        continue


    values=[]

    for interval in ["0-60","540-600"]:

        file=os.path.join(
            api_dir,
            interval+".txt"
        )


        if not os.path.exists(file):
            values.append("-")
            continue


        with open(file) as f:
            text=f.read()


        match=re.search(
            r"Covered branches: (\d+)",
            text
        )

        if match:
            values.append(match.group(1))
        else:
            values.append("-")


    print(
        f"{api}\t{values[0]}\t{values[1]}"
    )
