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

    pattern = load_bug_pattern(
        "experiment/EXP006_historical_bug_pattern_dataset/bug_patterns/torch.matmul/matmul_pattern_001.json"
    )

    print(pattern_to_prompt(pattern))
