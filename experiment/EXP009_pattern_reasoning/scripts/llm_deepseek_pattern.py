"""
LLM-driven test harness generator for PyTorch C++ (CPU).

EXP009:
Historical Bug Knowledge Reasoning Enhanced Harness Generation

Pipeline:

Historical Bug Reports
        |
        v
Historical Knowledge Abstraction
        |
        v
Knowledge-guided Prompt
        |
        v
LLM Reasoning
        |
        v
C++ libFuzzer Harness
"""
from __future__ import annotations

import argparse
import inspect
import json
import os
import re
import shutil
import time
import sys

from typing import Optional

import requests
import torch


# allow importing pattern adapter
sys.path.append(
    os.path.dirname(__file__)
)

from knowledge_loader import (
    load_knowledge,
    knowledge_to_prompt
)

from pathlib import Path

# ==========================
# Paths
# ==========================

DEFAULT_API_FILE = "api.txt"

HELPER_DIR = "../../testharness_generation/torch_cpu/torch_cpu_helper"


def here(*parts: str):
    return os.path.join(
        os.path.dirname(__file__),
        *parts
    )


# ==========================
# File utilities
# ==========================

def read_api_list(path):

    with open(path, "r") as f:
        return [
            line.strip()
            for line in f
            if line.strip()
        ]


def ensure_dir(path):

    os.makedirs(
        path,
        exist_ok=True
    )


def copy_helper_skeleton(src_dir, dst_dir):

    shutil.copytree(
        src_dir,
        dst_dir,
        dirs_exist_ok=True
    )


def load_helper_texts(helper_dir):

    main_cpp = open(
        os.path.join(helper_dir,"main.cpp")
    ).read()

    fuzz_cpp = open(
        os.path.join(helper_dir,"fuzzer_utils.cpp")
    ).read()

    fuzz_h = open(
        os.path.join(helper_dir,"fuzzer_utils.h")
    ).read()


    return (
        main_cpp,
        fuzz_cpp,
        fuzz_h
    )



# ==========================
# API information
# ==========================

def get_api_docstring(api_name):

    try:
        obj = eval(api_name)
    except Exception:
        return None

    try:
        return inspect.getdoc(obj)

    except Exception:
        return None



# ==========================
# Historical Bug Knowledge
# ==========================

def get_historical_knowledge_prompt(api_name):


    if api_name != "torch.matmul":

        return ""


    knowledge = load_knowledge(
        api_name
    )


    return knowledge_to_prompt(
        knowledge
    )

def load_prompt_template(path):

    with open(path,"r") as f:

        return f.read()

# ==========================
# Prompt construction
# ==========================

def build_prompt(
    api_name,
    helper_dir,
    include_docs=True
):

    main_cpp, fuzz_cpp, fuzz_h = load_helper_texts(
        helper_dir
    )

    knowledge_section = (
        get_historical_knowledge_prompt(
            api_name
        )
    )

    doc_section = ""

    if include_docs:

        doc = get_api_docstring(api_name)

        if doc:

            doc_section = (
                "\nAPI Reference (Python docstring):\n\n"
                + doc
                + "\n"
            )

        else:

            doc_section = (
                "\nAPI Reference not available.\n"
            )


    template_path = here(
        "prompt",
        "torch.matmul_reasoning_prompt.txt"
    )


    template = load_prompt_template(
        template_path
    )


    prompt = template.replace(
        "{API_DOC}",
        doc_section
    )


    prompt = prompt.replace(
        "{HISTORICAL_KNOWLEDGE}",
        knowledge_section
    )


    prompt += (

        "\n\nStarter skeletons for context:\n\n"

        + "```main.cpp\n"
        + main_cpp
        + "\n```\n\n"

        + "```fuzzer_utils.cpp\n"
        + fuzz_cpp
        + "\n```\n\n"

        + "```fuzzer_utils.h\n"
        + fuzz_h
        + "\n```\n"

    )

    return prompt


def extract_cpp_from_response(response_text):

    patterns = [

        re.compile(
            r"```cpp\s*(.*?)```",
            re.DOTALL |
            re.IGNORECASE
        ),

        re.compile(
            r"```c\+\+\s*(.*?)```",
            re.DOTALL |
            re.IGNORECASE
        ),

        re.compile(
            r"```\s*(.*?)```",
            re.DOTALL
        )

    ]


    for pat in patterns:

        m = pat.search(response_text)

        if m:

            return m.group(1).strip()


    return None




def call_deepseek(
    api_name,
    *,
    helper_dir,
    api_bases,
    api_key,
    model,
    max_tokens,
    temperature,
    include_docs=True,
    retries=3,
    retry_delay=10,
    timeout=180
):


    headers = {

        "Content-Type":
            "application/json",

        "Authorization":
            f"Bearer {api_key}"

    }



    prompt = build_prompt(
        api_name,
        helper_dir,
        include_docs
    )

    ##保存最终发送给 LLM 的 prompt，方便实验复现
    prompt_file = (
        "prompt/"
        + api_name.replace(".", "_")
        + "_reasoning_prompt_debug.txt"
    )

    with open(prompt_file, "w") as f:
        f.write(prompt)


    body = {

        "model": model,

        "messages": [

            {

                "role":
                    "system",

                "content":
                    (
                    "You are a senior C++ engineer "
                    "specializing in PyTorch libFuzzer targets. "
                    "Use historical bug knowledge as testing guidance. "
                    "Do not directly reproduce historical bugs. "
                    "Reason about underlying failure mechanisms "
                    "and generate diverse input strategies "
                    "to discover similar hidden bugs. "
                    "Return only one C++ code block."
                    )

            },

            {

                "role":
                    "user",

                "content":
                    prompt

            }

        ],


        "temperature":
            temperature,


        "max_tokens":
            max_tokens

    }



    url = api_bases[0].rstrip("/") + "/chat/completions"



    for attempt in range(retries):

        try:

            resp = requests.post(

                url,

                headers=headers,

                json=body,

                timeout=timeout

            )


            resp.raise_for_status()


            data = resp.json()


            content = (
                data["choices"]
                [0]
                ["message"]
                ["content"]
            )

            with open(
                "logs/raw_response.txt",
                "w"
            ) as f:
                f.write(content)

            cpp = extract_cpp_from_response(
                content
            )


            if cpp:

                return cpp


            print(
                "[ERROR] "
                "No cpp code extracted"
            )


        except Exception as e:


            print(
                f"[ERROR] DeepSeek failed: {e}"
            )


            time.sleep(
                retry_delay
            )



    return None




# ==========================
# Output
# ==========================


def write_output(
    out_base,
    api_name,
    cpp_code,
    *,
    overwrite,
    copy_helpers,
    helper_dir
):


    api_dir = os.path.join(
        out_base,
        api_name
    )


    if os.path.exists(api_dir) and not overwrite:

        print(
            f"[SKIP] {api_dir}"
        )

        return



    ensure_dir(api_dir)



    if copy_helpers:

        copy_helper_skeleton(
            helper_dir,
            api_dir
        )


    main_path = os.path.join(
        api_dir,
        "main.cpp"
    )


    with open(
        main_path,
        "w"
    ) as f:

        f.write(
            cpp_code
        )


    print(
        f"[OK] wrote {main_path}"
    )





# ==========================
# Arguments
# ==========================


def parse_args():

    p = argparse.ArgumentParser(
        description=
        "Generate PyTorch fuzz harness using DeepSeek"
    )


    p.add_argument(
        "--api-file",
        default=DEFAULT_API_FILE
    )


    p.add_argument(
        "--out-dir",
        default="."
    )


    p.add_argument(
        "--overwrite",
        action="store_true"
    )


    p.add_argument(
        "--no-helpers",
        action="store_true"
    )


    p.add_argument(
        "--no-docs",
        action="store_true"
    )


    p.add_argument(

        "--model",

        default=os.environ.get(

            "DEEPSEEK_MODEL",

            "deepseek-v4-pro"

        )

    )


    p.add_argument(

        "--api-base",

        default=os.environ.get(

            "DEEPSEEK_API_BASE",

            "https://api.deepseek.com"

        )

    )


    p.add_argument(

        "--api-key",

        default=os.environ.get(

            "DEEPSEEK_API_KEY"

        )

    )


    p.add_argument(

        "--max-tokens",

        type=int,

        default=8000

    )


    p.add_argument(

        "--temperature",

        type=float,

        default=0.2

    )


    return p.parse_args()




# ==========================
# Main
# ==========================


def main():


    args = parse_args()



    helper_dir = os.path.abspath(

        os.path.join(

            os.path.dirname(__file__),

            HELPER_DIR

        )

    )



    if not os.path.isdir(helper_dir):

        raise FileNotFoundError(

            f"Helper directory not found: {helper_dir}"

        )




    apis = read_api_list(

        args.api_file

    )



    api_bases = [

        args.api_base

    ]



    for api_name in apis:


        print(
            f"[GEN] {api_name}"
        )


        cpp = call_deepseek(

            api_name,

            helper_dir=helper_dir,

            api_bases=api_bases,

            api_key=args.api_key,

            model=args.model,

            max_tokens=args.max_tokens,

            temperature=args.temperature,

            include_docs=not args.no_docs

        )


        if not cpp:


            print(
                "[WARN] generation failed"
            )

            continue



        write_output(

            args.out_dir,

            api_name,

            cpp,

            overwrite=args.overwrite,

            copy_helpers=not args.no_helpers,

            helper_dir=helper_dir

        )



        time.sleep(1)




if __name__ == "__main__":

    main()
