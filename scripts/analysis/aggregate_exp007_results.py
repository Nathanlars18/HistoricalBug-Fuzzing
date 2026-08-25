import pandas as pd


INPUT = "results/processed/EXP007/baseline_final_summary.csv"

OUTPUT = "results/processed/EXP007/baseline_api_summary.csv"



def main():

    df = pd.read_csv(INPUT)


    summary = (
        df
        .groupby("api")
        .agg(
            avg_branch_coverage=(
                "branch_coverage",
                "mean"
            ),

            max_branch_coverage=(
                "branch_coverage",
                "max"
            ),

            avg_covered_branches=(
                "covered_branches",
                "mean"
            ),

            total_crashes=(
                "crash_count",
                "sum"
            ),

            total_unique_crashes=(
                "unique_crash_count",
                "sum"
            )
        )
        .reset_index()
    )


    summary.to_csv(
        OUTPUT,
        index=False
    )


    print("Saved:")
    print(OUTPUT)



if __name__ == "__main__":
    main()
