import csv


input_file = "../analysis/selected_bug_review.csv"

rows=[]


with open(input_file,"r",encoding="utf-8") as f:
    reader=csv.DictReader(f)

    for row in reader:
        row["human_include"]=""
        row["human_category"]=""
        row["human_pattern"]=""
        row["human_trigger"]=""
        row["harness_feasible"]=""
        row["review_note"]=""

        rows.append(row)



fieldnames=list(rows[0].keys())


with open(input_file,"w",encoding="utf-8",newline="") as f:

    writer=csv.DictWriter(
        f,
        fieldnames=fieldnames
    )

    writer.writeheader()
    writer.writerows(rows)


print("Updated:",input_file)
