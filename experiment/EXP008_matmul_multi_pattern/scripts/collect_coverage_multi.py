import os
import subprocess

BASE="/FlashFuzz/experiment/EXP008_matmul_multi_pattern/coverage/torch.matmul"

MODES=[
"multi"
]

INTERVALS = [
    "0-60",
    "60-120",
    "120-180",
    "180-240",
    "240-300"
]


OUT="multi_pattern_coverage_results.csv"

rows = []


for mode in MODES:

    mode_dir = os.path.join(BASE, mode)

    for interval in INTERVALS:

        profraw = os.path.join(
            mode_dir,
            "coverage_data",
            interval,
            "torch.matmul.profraw"
        )


        if not os.path.exists(profraw):
            print("Missing:", profraw)
            continue


        profdata = os.path.join(
            mode_dir,
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


        outfile = os.path.join(
            mode_dir,
            f"{interval}.txt"
        )


        subprocess.run(
            [
                "python3",
                "/FlashFuzz/scripts/get_coverage_results.py",
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
            content=f.read()


        rows.append(
            [
                "torch.matmul",
                mode,
                interval,
                content.strip()
            ]
        )


with open(OUT,"w") as f:

    f.write(
        "api,mode,interval,coverage\n"
    )

    for r in rows:
        f.write(",".join(r)+"\n")


print("Finished")
