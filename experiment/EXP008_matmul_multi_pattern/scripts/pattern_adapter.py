import json


def load_bug_pattern(path):

    with open(path, "r") as f:
        return json.load(f)



def pattern_to_prompt(pattern):

    text = f"""
Historical bug information:

API:
{pattern['api']}

Bug category:
{', '.join(pattern['bug_category'])}

Pattern abstraction:

API specific pattern:
{pattern['pattern_abstraction']['api_specific_pattern']}

General category:
{pattern['pattern_abstraction']['general_category']}

Transferability:
{pattern['pattern_abstraction']['transferability']}

Trigger conditions:
"""

    trigger = pattern["trigger_condition"]

    for key, value in trigger.items():
        text += f"""
- {key}: {value}
"""


    text += f"""

Root cause:
{pattern['root_cause']['description']}


Bug oracle:
{pattern['bug_oracle']['type']}


Harness generation guidance:
"""

    for item in pattern["harness_strategy"]["constraints"]:
        text += f"""
- {item}
"""

    return text



if __name__ == "__main__":

    from pathlib import Path

    pattern_path = (
        Path(__file__).resolve()
        .parents[1]
        /
        "EXP006_historical_bug_pattern_dataset"
        /
        "bug_patterns"
        /
        "torch.matmul"
        /
        "matmul_pattern_001.json"
    )
    pattern = load_bug_pattern(pattern_path)

    print(pattern_to_prompt(pattern))
