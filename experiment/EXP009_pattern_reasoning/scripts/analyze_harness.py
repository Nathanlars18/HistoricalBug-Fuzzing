import re
import json


HARNESS_PATH = "results/exp009_reasoning_main.cpp"


# Historical bug reproduction indicators
direct_patterns = {

    "unaligned_memory":
    [
        "data_ptr",
        "unaligned",
        "alignment",
        "from_blob"
    ],


    "zero_dimension":
    [
        "size(0) == 0",
        "size(1) == 0",
        "sizes = {0",
        "sizes={0",
        "numel() == 0",
        "numel()==0",
        "reshape({0",
        "view({0"
    ],
    "specific_shape":
    [
        "M=1",
        "shape=(1",
        "size(0)==1"
    ],


    "storage_violation":
    [
        "sentinel",
        "storage_offset",
        "unsafe",
        "out.resize"
    ]
}


def analyze():

    with open(
        HARNESS_PATH,
        "r"
    ) as f:

        code=f.read()


    result={}


    for category, keywords in direct_patterns.items():

        matched=[]

        for k in keywords:

            if k in code:

                matched.append(k)


        result[category]=matched



    direct=False


    for v in result.values():

        if len(v)>0:

            direct=True



    print("="*60)

    print("Harness Pattern Analysis")

    print("="*60)



    for k,v in result.items():

        print(
            f"{k}: {v}"
        )


    print()


    if direct:

        print(
            "Direct reproduction indicators detected"
        )

    else:

        print(
            "No obvious direct reproduction indicators"
        )


    print("="*60)



if __name__=="__main__":

    analyze()
