import argparse
import os
import json
import time
import requests
import re


def extract_json(text):

    if text is None:
        return None


    # 去掉markdown
    text = re.sub(
        r"```json",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"```",
        "",
        text
    )


    # 找所有可能JSON对象
    matches = re.findall(
        r"\{.*?\}",
        text,
        re.DOTALL
    )


    for m in matches:

        try:

            json.loads(m)

            return m

        except Exception:

            continue


    return None


def call_deepseek(
    prompt,
    api_key,
    model="deepseek-v4-pro",
    max_tokens=8192,
    temperature=0.1,
    retries=5,
    timeout=180
):

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }


    body = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }


    for i in range(retries):

        try:

            response = requests.post(
                "https://api.deepseek.com/chat/completions",
                headers=headers,
                json=body,
                timeout=timeout
            )


            response.raise_for_status()


            result = response.json()


            print(
                "[DEBUG RESPONSE]",
                json.dumps(
                    result,
                    ensure_ascii=False
                )[:1000]
            )


            message = (
                result
                .get("choices",[{}])[0]
                .get("message",{})
            )


            content = message.get(
                "content",
                ""
            )


            if not content.strip():

                reasoning = message.get(
                    "reasoning_content",
                    ""
                )


                json_part = extract_json(
                    reasoning
                )


                if json_part:

                    content = json_part

                else:

                    content = reasoning

            if not content.strip():

                raise Exception(
                    "Empty response from DeepSeek"
                )


            return content



        except Exception as e:

            print(
                f"[Retry {i+1}/{retries}] DeepSeek error:",
                e
            )

            time.sleep(10)



    return None




def build_prompt(bug_text):


    BASE_DIR = os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )


    prompt_file = os.path.join(
        BASE_DIR,
        "analysis",
        "bug_selection_prompt.md"
    )

    with open(

        prompt_file,

        "r",

        encoding="utf-8"

    ) as f:

        template = f.read()



    # avoid extremely long issue reports

    if len(bug_text) > 25000:

        bug_text = (
            bug_text[:25000]
            +
            "\n\n[TRUNCATED]"
        )



    prompt = template.replace(

        "{bug_report}",

        bug_text

    )


    return prompt






def main():


    parser = argparse.ArgumentParser()



    parser.add_argument(

        "--api_key",

        required=True

    )


    parser.add_argument(

        "--model",

        default="deepseek-v4-pro"

    )


    parser.add_argument(

        "--bug_id",

        required=True

    )



    args = parser.parse_args()



    report_file = (

        "../raw_reports/"

        +

        args.bug_id

        +

        "_summary_with_code.txt"

    )



    if not os.path.exists(report_file):

        print(

            "Bug report not found:",

            report_file

        )

        return



    with open(

        report_file,

        "r",

        encoding="utf-8"

    ) as f:

        bug_text = f.read()



    prompt = build_prompt(

        bug_text

    )



    print(

        "[LLM] analyzing bug:",

        args.bug_id

    )



    response = call_deepseek(

        prompt,

        args.api_key,

        args.model

    )



    if response is None:


        print(

            "LLM failed"

        )


        return



    print(response)



    # parse JSON


    json_text = extract_json(

        response

    )


    if json_text is None:


        parsed_response = {

            "bug_id": args.bug_id,

            "parse_error": True,

            "raw_response": response
        }

    else:


        try:

            parsed_response = json.loads(

                json_text

            )


        except Exception as e:


            print(

                "JSON parse failed:",

                e

            )


            parsed_response = {

                "parse_error":

                    True,

                "raw_response":

                    response

            }




    parsed_response["bug_id"] = (

        args.bug_id

    )

    required_fields = [
        "target_api",
        "bug_category",
        "trigger_condition",
        "oracle_type",
        "pattern_extractability",
        "knowledge_generation_feasibility",
        "include",
        "confidence",
        "reason"
    ]


    for field in required_fields:

        if field not in parsed_response:
 
            parsed_response[field] = ""

    output_dir = (

        "../analysis/llm_raw_response"

    )


    os.makedirs(

        output_dir,

        exist_ok=True

    )


    output_file = (

        output_dir

        +

        "/"

        +

        args.bug_id

        +

        ".json"

    )



    with open(

        output_file,

        "w",

        encoding="utf-8"

    ) as f:


        json.dump(

            parsed_response,

            f,

            indent=4,

            ensure_ascii=False

        )



    print(

        "Saved:",

        output_file

    )





if __name__ == "__main__":

    main()
