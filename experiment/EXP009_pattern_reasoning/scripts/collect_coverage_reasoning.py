import os
import subprocess


# EXP009 coverage 数据位置
BASE="/workspace/exp009/results"

INTERVALS = [
    "0-60",
    "60-120",
    "120-180",
    "180-240",
    "240-300",
    "300-360",
    "360-420",
    "420-480",
    "480-540",
    "540-600"
]


OUT = "reasoning_pattern_coverage_results.csv"


rows = []


for interval in INTERVALS:

    print("=" * 60)
    print("Processing:", interval)


    # 原始 coverage 数据
    profraw = os.path.join(
        BASE,
        "coverage_data",
        interval,
        "torch.matmul.profraw"
    )


    if not os.path.exists(profraw):

        print("Missing:", profraw)

        continue



    # 合并 profraw
    profdata = os.path.join(
        BASE,
        "coverage_data",
        f"{interval}.profdata"
    )


    subprocess.run(
        [
            "llvm-profdata",
            "merge",
            "-sparse",
            profraw,
            "-o",
            profdata
        ],
        check=True
    )



    # coverage 输出文件
    outfile = os.path.join(
        BASE,
        "coverage_data",
        f"{interval}.txt"
    )



    subprocess.run(
        [
            "python3",
            "/root/fuzz/get_coverage_results.py",

            "--binary",
            "/root/pytorch/build-fuzz/lib/libtorch_cpu.so",

            "--dll",
            "torch",

            "--require",
            "aten/src/ATen/native",

            "--coverage_file",
            profdata,

            "--out",
            outfile
        ],
        check=True
    )



    with open(outfile) as f:

        content = f.read()



    rows.append(
        [
            "torch.matmul",
            "reasoning",
            interval,
            content.strip()
        ]
    )



with open(OUT, "w") as f:

    f.write(
        "api,mode,interval,coverage\n"
    )


    for r in rows:

        f.write(
            ",".join(r) + "\n"
        )



print("=" * 60)
print("Finished")
print("Output:", OUT)
