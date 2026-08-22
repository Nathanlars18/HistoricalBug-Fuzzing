import os
import json
import argparse
import requests
import re


BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)


EXP006_DIR = os.path.dirname(BASE_DIR)


BUG_REPORT_DIR = os.path.join(
    EXP006_DIR,
    "bug_reports"
)


OUTPUT_DIR = os.path.join(
    EXP006_DIR,
    "bug_patterns_test"
)


SCHEMA_FILE = os.path.join(
    EXP006_DIR,
    "pattern_schema.md"
)


MAPPING_FILE = os.path.join(
    EXP006_DIR,
    "report_to_pattern_mapping.md"
)


MODEL = "deepseek-v4-pro"


API_URL = "https://api.deepseek.com/chat/completions"



def load_file(path):

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return f.read()



def call_deepseek(prompt, api_key):

    headers = {
        "Authorization":
            f"Bearer {api_key}",

        "Content-Type":
            "application/json"
    }


    body = {

        "model": MODEL,

        "messages":[
            {
                "role":"user",
                "content":prompt
            }
        ],

        "temperature":0.2
    }


    response = requests.post(
        API_URL,
        headers=headers,
        json=body,
        timeout=120
    )


    response.raise_for_status()


    result=response.json()


    content = result["choices"][0]["message"]["content"]


    return content



def extract_json(text):

    """
    防止DeepSeek返回markdown代码块
    """

    text=text.strip()


    if "```json" in text:

        text=text.split(
            "```json"
        )[1]

        text=text.split(
            "```"
        )[0]


    return json.loads(
        text.strip()
    )


def normalize_pattern(pattern):


    # ==========================
    # normalize source
    # ==========================

    metadata = pattern.get(
        "metadata",
        {}
    )


    if not isinstance(metadata, dict):

        metadata = {}

        pattern["metadata"] = metadata



    source = metadata.get(
        "source",
        {}
    )


    if not isinstance(source, dict):

        metadata["source"] = {}

        source = metadata["source"]

    source_map = {

        "github_issue":
        "GitHub Issue",

        "bug_report":
        "GitHub Issue",

        "GitHub issue":
        "GitHub Issue",

        "github issue":
        "GitHub Issue"

    }


    if source.get("type") in source_map:

        source["type"] = source_map[
            source["type"]
        ]



    # ==========================
    # normalize category
    # ==========================

    category_map = {

        "shape_boundary":
        "Shape Boundary",

        "dtype_boundary":
        "Dtype Boundary",

        "device_transition":
        "Device Transition",

        "memory_layout":
        "Memory Layout",

        "memory_layout_boundary":
        "Memory Layout Boundary",

        "backend_dispatch":
        "Backend Dispatch",

        "numerical_edge_case":
        "Numerical Edge Case"

    }


    category = pattern.get(
        "bug_category",
        {}
    )

    if not isinstance(category, dict):

        pattern["bug_category"] = {
            "primary_category": category,
            "secondary_category": ""
        }

        category = pattern["bug_category"]

    if isinstance(category, dict):

        for key in [
            "primary_category",
            "secondary_category"
        ]:

            if key in category:

                value = category[key]

                if value in category_map:

                    category[key] = category_map[value]




    # ==========================
    # normalize oracle
    # ==========================

    oracle_map = {

        "wrong_result":
        "Incorrect Output",

        "Wrong Result":
        "Incorrect Output",

        "wrong output":
        "Incorrect Output",

        "memory corruption":
        "Memory Error",

        "Memory Corruption":
        "Memory Error"

    }


    oracle = pattern.get(
        "bug_oracle",
        {}
    )

    if not isinstance(oracle, dict):

        pattern["bug_oracle"] = {
            "type": oracle,
            "description": "",
            "signal": "",
            "exit_code": ""
        }

        oracle = pattern["bug_oracle"]

    if oracle.get("type") in oracle_map:

        oracle["type"] = oracle_map[
            oracle["type"]
        ]

    # ==========================
    # normalize trigger_condition
    # ==========================

    trigger = pattern.get(
        "trigger_condition",
        {}
    )


    if not isinstance(trigger, dict):

        pattern["trigger_condition"] = {}

        trigger = pattern["trigger_condition"]



    for key in [
        "shape_trigger",
        "dtype_trigger",
        "device_trigger",
        "memory_trigger",
        "value_trigger",
        "state_trigger",
        "execution_trigger",
        "concrete_constraints"
    ]:

        if key in trigger:

            value = trigger[key]

            if isinstance(value, bool):

                trigger[key] = ""


    return pattern

def validate_pattern(pattern):


    required_fields = [

        "metadata",

        "bug_category",

        "pattern_abstraction",

        "trigger_condition",

        "root_cause",

        "bug_oracle",

        "harness_strategy",

        "verification_status"

    ]


    for field in required_fields:

        if field not in pattern:

            return False, f"Missing {field}"



    metadata = pattern["metadata"]


    if "api_name" not in metadata:

        return False, "Missing api_name"



    if "source" not in metadata:

        return False, "Missing source"

    if "source_report" not in metadata:

        return False, "Missing source_report"

    oracle = pattern["bug_oracle"]


    allowed_oracle = [

        "Crash",

        "Exception",

        "Incorrect Output",

        "Timeout/Hang",

        "Memory Error"

    ]


    oracle_type = oracle.get(
        "type",
        ""
    )


    if oracle_type not in allowed_oracle:

        return False, (
            f"Invalid oracle {oracle_type}"
        )


    for field in [

        "description",

        "signal",

        "exit_code"

    ]:

        if field not in oracle:

            return False, (
                f"Missing oracle field {field}"
            )



    root = pattern["root_cause"]


    if root.get("confidence") == "high":

        layers = [

            "api_layer",

            "aten_layer",

            "kernel_layer",

            "backend_layer",

            "numerical_layer"

        ]


        if all(
            root.get(x,"")==""
            for x in layers
        ):

            root["confidence"]="low"

    # =====================================
    # Reduce confidence for user-reported bugs
    # without official root cause evidence
    # =====================================

    verification = pattern.get(
        "verification_status",
        {}
    )


    root = pattern.get(
        "root_cause",
        {}
    )


    if (
        verification.get("level")
        ==
        "user_reported"
        and
        root.get("confidence")
        ==
        "high"
    ):

        root["confidence"] = "medium"

    return True,"OK"

def build_prompt(report, schema, mapping):

    prompt=f"""
You are a researcher building a historical bug pattern database
for deep learning framework fuzzing.

Your task is to transform one historical bug report into a reusable
bug pattern that can guide automated harness generation.

The goal is NOT to reproduce the original bug only.
The goal is to extract general testing knowledge from the bug.

You are provided with:

1. Pattern Schema:
{schema}

2. Report-to-Pattern Mapping Rules:
{mapping}

3. Historical Bug Report:
{json.dumps(report, indent=2)}


====================

Output Requirements:

1. Output JSON only.
Do not output markdown or explanations.

2. Strictly follow the provided pattern schema.

The root JSON structure must exactly contain:

{{
"metadata": {{}},
"bug_category": {{}},
"pattern_abstraction": {{}},
"trigger_condition": {{}},
"root_cause": {{}},
"bug_oracle": {{}},
"harness_strategy": {{}},
"verification_status": {{}}
}}


3. Do not create additional fields.
Do not remove required fields.

4. Use snake_case for JSON keys.

5. Missing information:

Use empty strings.

Do not invent unsupported facts.


6. Source information:

The source information may appear in different forms in the bug report,
such as:

- source
- source_information
- repository information


Normalize source information into:

{{
"type":"",
"id":"",
"repository":""
}}


The source type should describe the origin of the bug report,
for example:

"GitHub Issue"


If source information is unavailable,
leave the fields empty.

If a bug identifier is available in the report,
store it in source.id.

Do not add "#" prefix.
====================

Bug Category Rules:

bug_category values must use only:

Shape Boundary
Dtype Boundary
Device Transition
Memory Layout Boundary
Numerical Edge Case
Gradient State Boundary
Backend Dispatch Boundary
Execution State Boundary
Graph Transformation Boundary
API Contract Boundary

Do not use lowercase or snake_case category names.

Select bug_category based on the violated testing boundary,
not the implementation backend.

For example:
Invalid argument values, unsupported enum values,
and missing parameter validation should use:

API Contract Boundary

rather than Backend Dispatch Boundary.

====================

Bug Oracle Rules:

bug_oracle must always be an object:

{{
"type":"",
"description":"",
"signal":"",
"exit_code":""
}}

type must be exactly one of:

Crash
Exception
Incorrect Output
Timeout/Hang
Memory Error


====================

Root Cause Rules:

Only fill root cause layers supported by:
- bug report
- issue description
- fix information

If the report only describes symptoms
and does not provide implementation details,
do not infer root cause layers.

For example:
"shape check missing"
should not be considered a confirmed root cause
unless the issue or fix explicitly states it.

Use medium or low confidence for inferred explanations.

Do not infer unsupported implementation details.

Confidence:

high:
explicitly confirmed by report or fix.

medium:
strongly implied.

low:
only inferred by the model.

If root cause information is missing,
confidence must be low.


====================

Pattern Abstraction Rules:

The pattern should describe a reusable bug mechanism,
not a single issue reproduction.

api_specific_pattern should represent the defect mechanism.

Avoid including:

- issue number
- exact tensor values
- exact reproduction script
- crash signal

Avoid over-specialized names.

Bad:
torch_matmul_fp32_cpu_sigbus_issue191238

Good:
torch_matmul_unaligned_memory_access_bug


Trigger conditions may include:
- shape
- dtype
- device
- memory layout

when they are necessary to describe the bug.


====================

Harness Strategy Rules:

Describe how a fuzzing harness can generate
inputs that may expose similar bugs.

Prefer general strategies over exact reproduction steps.

"""
    return prompt


def normalize_api(api):

    return api.replace(
        ".",
        "_"
    )

def get_existing_pattern_id(output_api):

    max_id = 0


    for filename in os.listdir(output_api):

        match = re.search(
            r"pattern_(\d+)",
            filename
        )

        if match:

            max_id=max(
                max_id,
                int(match.group(1))
            )


    return max_id


def process_api(api, api_key, output_dir):

    input_dir = os.path.join(
        BUG_REPORT_DIR,
        api
    )

    output_api = os.path.join(
        output_dir,
        api
    )

    os.makedirs(
        output_api,
        exist_ok=True
    )

    schema = load_file(
        SCHEMA_FILE
    )

    mapping = load_file(
        MAPPING_FILE
    )

    count = 0

    existing = len(
        os.listdir(output_api)
    )


    for filename in sorted(
        os.listdir(input_dir)
    ):

        if not filename.endswith(".json"):
            continue


        pattern_name = filename.replace(
            ".json",
            ""
        )


        already_exists=False


        for f in os.listdir(output_api):

            if not f.endswith(".json"):
                continue


            old_path=os.path.join(
                output_api,
                f
            )


            try:

                with open(
                    old_path,
                    encoding="utf-8"
                ) as fp:

                    old_pattern=json.load(fp)


                old_report = old_pattern.get(
                    "metadata",
                    {}
                ).get(
                    "source_report",
                    ""
                )


                if old_report == filename:

                    already_exists=True

                    break


            except Exception:

                continue

        if already_exists:

            print(
                "Skip existing:",
                filename
            )

            continue



        report_path = os.path.join(
            input_dir,
            filename
        )


        with open(
            report_path,
            encoding="utf-8"
        ) as f:

            report = json.load(f)



        print(
            "Processing:",
            filename
        )



        prompt = build_prompt(
            report,
            schema,
            mapping
        )



        try:

            result = call_deepseek(
                prompt,
                api_key
            )


        except Exception as e:

            print(
                "DeepSeek failed:",
                filename,
                e
            )

            continue



        try:

            pattern = extract_json(
                result
            )


            pattern = normalize_pattern(
                pattern
            )


            valid, msg = validate_pattern(
                pattern
            )


            if not valid:

                print(
                    "Validation failed:",
                    filename,
                    msg
                )

                continue



        except Exception as e:

            print(
                "Pattern processing failed:",
                filename,
                e
            )

            continue



        # generate pattern id
        pattern_id = existing + count + 1



        # make sure metadata exists
        if "metadata" not in pattern:

            pattern["metadata"] = {}



        pattern["metadata"]["pattern_id"] = (
            f"{normalize_api(api)}_pattern_{pattern_id:03d}"
        )

        pattern["metadata"]["source_report"] = filename

        output = os.path.join(
            output_api,
            f"{normalize_api(api)}_pattern_{pattern_id:03d}.json"
        )



        with open(
            output,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                pattern,
                f,
                indent=4,
                ensure_ascii=False
            )



        count += 1



    print(
        "Generated patterns:",
        count
    )


if __name__=="__main__":


    parser=argparse.ArgumentParser()


    parser.add_argument(
        "--api",
        required=True
    )

    parser.add_argument(
        "--output",
        default="bug_patterns_test"
    )

    parser.add_argument(
        "--api_key",
        default=os.environ.get(
            "DEEPSEEK_API_KEY"
        )
    )


    args=parser.parse_args()



    if not args.api_key:

        raise RuntimeError(
            "Missing DEEPSEEK_API_KEY"
        )



    process_api(
        args.api,
        args.api_key,
        args.output
    )
