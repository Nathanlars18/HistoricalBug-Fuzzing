import os
import sys


# 当前scripts目录加入路径
sys.path.append(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)


from build_knowledge_json import process_api


PATTERN_DIR="bug_patterns"


def main():

    api_key=os.environ.get(
        "DEEPSEEK_API_KEY"
    )


    if not api_key:

        raise RuntimeError(
            "Missing DEEPSEEK_API_KEY"
        )


    apis=sorted(
        os.listdir(
            PATTERN_DIR
        )
    )


    total=0


    for api in apis:


        api_path=os.path.join(
            PATTERN_DIR,
            api
        )


        # 防止非目录文件
        if not os.path.isdir(api_path):

            continue


        print(
            "\n===================="
        )

        print(
            "Processing API:",
            api
        )


        try:

            process_api(
                api,
                api_key
            )


            total+=1


        except Exception as e:

            print(
                "Failed API:",
                api,
                e
            )


    print(
        "\nFinished APIs:",
        total
    )



if __name__=="__main__":

    main()
