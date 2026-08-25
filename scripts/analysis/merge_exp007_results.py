import pandas as pd
import os


FUZZ_CSV = "results/processed/EXP007/baseline_summary.csv"

COVERAGE_CSV = "results/processed/EXP007/baseline_coverage_summary.csv"

OUTPUT = "results/processed/EXP007/baseline_final_summary.csv"



def main():

    # 读取 fuzz
    fuzz = pd.read_csv(FUZZ_CSV)


    # 删除空coverage字段
    fuzz = fuzz.drop(
        columns=[
            "covered_lines",
            "total_lines",
            "line_coverage"
        ],
        errors="ignore"
    )


    # 读取coverage
    coverage = pd.read_csv(
        COVERAGE_CSV
    )


    # 合并
    result = fuzz.merge(
        coverage,
        on=[
            "api",
            "run"
        ],
        how="left"
    )


    os.makedirs(
        os.path.dirname(OUTPUT),
        exist_ok=True
    )


    result.to_csv(
        OUTPUT,
        index=False
    )


    print("Saved:")
    print(OUTPUT)



if __name__ == "__main__":
    main()
