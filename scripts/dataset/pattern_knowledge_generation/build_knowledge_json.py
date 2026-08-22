import os
import json
import argparse
import requests
import time

PATTERN_DIR = "bug_patterns"

OUTPUT_DIR = "knowledge_base"

SCHEMA_FILE = "knowledge_schema.md"

RULE_FILE = "pattern_to_knowledge_rules.md"

def load_file(path):

    with open(
        path,
        encoding="utf-8"
    ) as f:
        return f.read()

def call_deepseek(prompt, api_key):

    url = "https://api.deepseek.com/chat/completions"


    headers = {
        "Authorization":
        f"Bearer {api_key}",

        "Content-Type":
        "application/json"
    }


    data = {

        "model":
        "deepseek-v4-pro",

        "messages":[
            {
                "role":"user",
                "content":prompt
            }
        ],

        "temperature":0.2
    }


    max_retry = 3


    for attempt in range(max_retry):

        try:

            response=requests.post(
                url,
                headers=headers,
                json=data,
                timeout=180
            )


            response.raise_for_status()


            return response.json()["choices"][0]["message"]["content"]


        except Exception as e:

            print(
                f"DeepSeek retry {attempt+1}/{max_retry}:",
                e
            )

            time.sleep(10)



    raise RuntimeError(
        "DeepSeek request failed after retries"
    )


def build_prompt(pattern, schema, rules):


    prompt=f"""

You are constructing a historical bug knowledge base
for deep learning framework fuzzing.


Your task:

Transform one bug pattern into reusable testing knowledge
that can guide LLM-based harness generation.


The knowledge should:

1. Abstract the underlying testing principle.

2. Avoid reproducing one specific historical bug.

3. Provide general exploration strategies.

4. Preserve the connection with the source pattern.


Provided:

Knowledge Schema:

{schema}


Pattern-to-Knowledge Rules:

{rules}


Input Pattern:

{json.dumps(pattern,indent=2)}



Output Requirements:


1. Output JSON only.

2. Strictly follow knowledge_schema.md.

3. Do not create extra fields.

4. Do not remove required fields.

5. Use empty string when information is unavailable.

6. Avoid literal reproduction of issue.


Important:


Do not generate:

- issue-specific test cases
- exact tensor values
- exact reproduction scripts


Generate:

- general bug principle
- risk dimensions
- testing insights
- transferable testing strategy

transferability must explain why this knowledge
can or cannot apply to other APIs.

Do not judge transferability only from the original API.


The JSON structure must exactly be:


{{
"metadata": {{}},

"knowledge_abstraction": {{}},

"risk_dimensions": {{}},

"failure_mechanism": {{}},

"testing_insights": {{}},

"transferability": {{}},

"llm_reasoning_guidance": {{}}

}}

All JSON keys must strictly use lowercase snake_case.

Do not use:
- Title Case keys
- CamelCase keys
- Keys containing spaces

Examples:

Correct:
"bug_theme"
"general_principle"
"source_pattern_id"

Incorrect:
"Bug Theme"
"General Principle"
"Source Pattern ID"

Some fields have strict formats:

1. risk_category must always be a JSON array.

Correct:

[
"Memory Layout Boundary"
]

Incorrect:

"Memory Layout Boundary"

testing_insights must use JSON arrays.

The following fields must be arrays:

- input_exploration
- constraint_awareness
- oracle_strategy


Correct:

"input_exploration":[
"Explore zero dimension tensors",
"Vary dtype combinations"
]


Incorrect:

"input_exploration":
"Explore zero dimension tensors"

avoid_literal_reproduction must be boolean.

Allowed values:

true

false


Do not output explanation strings.


"""


    return prompt

def extract_json(text):

    start=text.find("{")

    end=text.rfind("}")

    return json.loads(
        text[start:end+1]
    )

def normalize_knowledge(k):


    # =========================
    # metadata normalization
    # =========================

    if "metadata" not in k:
        k["metadata"] = {}


    metadata = k["metadata"]


    rename_map = {

        "Knowledge ID":
        "knowledge_id",

        "Source Pattern ID":
        "source_pattern_id",

        "Source Report":
        "source_report",

        "API Name":
        "api_name",

        "Original Issue":
        "original_issue",

        "Confidence":
        "confidence",

        "Verification Status":
        "verification_status"

    }


    for old,new in rename_map.items():

        if old in metadata:

            metadata[new] = metadata.pop(old)



    metadata_defaults = {

        "knowledge_id":"",
        "source_pattern_id":"",
        "source_report":"",
        "api_name":"",
        "original_issue":"",
        "verification_status":"",
        "confidence":"low"

    }


    for key,value in metadata_defaults.items():

        if key not in metadata:

            metadata[key]=value



    # =========================
    # transferability
    # =========================

    if "transferability" not in k:

        k["transferability"]={

            "level":"low",

            "reason":""

        }



    # =========================
    # risk_category normalization
    # =========================


    if "knowledge_abstraction" in k:


        category = k["knowledge_abstraction"].get(
            "risk_category",
            []
        )


        if isinstance(category,str):

            k["knowledge_abstraction"]["risk_category"]=[
                category
            ]


        elif category is None:

            k["knowledge_abstraction"]["risk_category"]=[]



    # =========================
    # testing_insights normalization
    # =========================


    if "testing_insights" in k:


        for field in [

            "input_exploration",

            "constraint_awareness",

            "oracle_strategy"

        ]:


            value = k["testing_insights"].get(
                field,
                []
            )


            if isinstance(value,str):

                k["testing_insights"][field]=[
                    value
                ]


            elif value is None:

                k["testing_insights"][field]=[]



    # =========================
    # avoid_literal_reproduction
    # =========================

    if "llm_reasoning_guidance" in k:


        value=k["llm_reasoning_guidance"].get(
            "avoid_literal_reproduction",
            False
        )


        if isinstance(value,str):

            k["llm_reasoning_guidance"][
                "avoid_literal_reproduction"
            ]=True



        strategy=k["llm_reasoning_guidance"].get(
            "generation_strategy",
            []
        )


        if isinstance(strategy,str):

            k["llm_reasoning_guidance"][
                "generation_strategy"
            ]=[
                strategy
            ]


        elif strategy is None:

            k["llm_reasoning_guidance"][
                "generation_strategy"
            ]=[]

    return k

def validate_knowledge(k):


    required=[

        "metadata",

        "knowledge_abstraction",

        "risk_dimensions",

        "failure_mechanism",

        "testing_insights",

        "transferability",

        "llm_reasoning_guidance"

    ]


    for field in required:


        if field not in k:

            return False, field



    # metadata必须是对象

    if not isinstance(
        k["metadata"],
        dict
    ):

        return False,"metadata"



    # testing_insights必须是对象

    if not isinstance(
        k["testing_insights"],
        dict
    ):

        return False,"testing_insights"



    # transferability必须是对象

    if not isinstance(
        k["transferability"],
        dict
    ):

        return False,"transferability"



    # risk_category如果存在必须是list

    if "knowledge_abstraction" in k:


        category=k["knowledge_abstraction"].get(
            "risk_category",
            []
        )


        if not isinstance(
            category,
            list
        ):

            return False,"risk_category"



    return True,"OK"

def process_api(api, api_key):

    input_dir=os.path.join(
        PATTERN_DIR,
        api
    )


    output_dir=os.path.join(
        OUTPUT_DIR,
        api
    )


    os.makedirs(
        output_dir,
        exist_ok=True
    )


    schema=load_file(
        SCHEMA_FILE
    )


    rules=load_file(
        RULE_FILE
    )


    count=0


    existing_count=len(
        os.listdir(output_dir)
    )


    for filename in sorted(
        os.listdir(input_dir)
    ):


        if not filename.endswith(".json"):

            continue



        knowledge_name = filename.replace(
            "_pattern",
            "_knowledge"
        )


        already_exists=False


        for f in os.listdir(output_dir):

            if knowledge_name.replace(
                ".json",
                ""
            ) in f:

                already_exists=True



        if already_exists:

            print(
                "Skip existing:",
                filename
            )

            continue



        print(
            "Processing:",
            filename
        )


        with open(
            os.path.join(
                input_dir,
                filename
            ),
            encoding="utf-8"
        ) as f:

            pattern=json.load(f)



        prompt=build_prompt(
            pattern,
            schema,
            rules
        )


        try:

            result=call_deepseek(
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

            knowledge=extract_json(
                result
            )


        except Exception as e:

            print(
                "JSON extraction failed:",
                filename,
                e
            )

            continue



        try:

            knowledge=normalize_knowledge(
                knowledge
            )


        except Exception as e:

            print(
                "Normalize failed:",
                filename,
                e
            )

            continue



        valid,msg=validate_knowledge(
            knowledge
        )


        if not valid:

            print(
                "Validation failed:",
                filename,
                msg
            )

            continue



        knowledge_id=f"{api.replace('.','_')}_knowledge_{existing_count+count+1:03d}"


        knowledge["metadata"]["knowledge_id"]=knowledge_id


        output=os.path.join(
            output_dir,
            knowledge_id+".json"
        )


        with open(
            output,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                knowledge,
                f,
                indent=4,
                ensure_ascii=False
            )


        count+=1



    print(
        "Generated knowledge:",
        count
    )


if __name__=="__main__":


    parser=argparse.ArgumentParser()


    parser.add_argument(
        "--api",
        required=True
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
        args.api_key
    )

