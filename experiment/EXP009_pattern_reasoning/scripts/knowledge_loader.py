import json
import os


KNOWLEDGE_PATH = (
    "../EXP006_historical_bug_pattern_dataset/"
    "knowledge_base"
)



def load_knowledge(api):


    api_path = os.path.join(
        KNOWLEDGE_PATH,
        api
    )


    if not os.path.exists(api_path):

        return []


    knowledge_list = []


    for file in sorted(os.listdir(api_path)):


        if file.endswith(".json"):


            with open(
                os.path.join(api_path,file),
                "r"
            ) as f:

                knowledge_list.append(
                    json.load(f)
                )


    return knowledge_list





def knowledge_to_prompt(knowledge_list):


    prompt = ""


    for item in knowledge_list:


        meta = item["metadata"]

        abstraction = item["knowledge_abstraction"]

        risks = item["risk_dimensions"]

        mechanism = item["failure_mechanism"]

        testing = item["testing_insights"]

        transfer = item["transferability"]

        guidance = item["llm_reasoning_guidance"]



        prompt += "\n"
        prompt += "="*60
        prompt += "\nHistorical Bug Knowledge\n"
        prompt += "="*60
        prompt += "\n"



        prompt += (
            "\nAPI:\n"
            + meta["api"]
        )


        prompt += (
            "\nSource Issue:\n"
            + meta["original_issue"]
        )



        prompt += (
            "\n\nBug Theme:\n"
            + abstraction["bug_theme"]
        )


        prompt += (
            "\n\nGeneral Principle:\n"
            + abstraction["general_principle"]
        )


        prompt += (
            "\n\nRisk Category:\n"
            + str(
                abstraction["risk_category"]
            )
        )



        prompt += "\n\nRisk Dimensions:\n"


        for k,v in risks.items():

            prompt += (
                f"- {k}: {v}\n"
            )



        prompt += "\nFailure Mechanism:\n"


        prompt += (
            "Layer: "
            + mechanism["layer"]
            + "\n"
        )


        prompt += (
            "Description: "
            + mechanism["description"]
            + "\n"
        )



        prompt += "\nTesting Insights:\n"


        for section in [
            "input_exploration",
            "constraint_awareness",
            "oracle_strategy"
        ]:


            prompt += (
                "\n"
                + section
                + ":\n"
            )


            for x in testing[section]:

                prompt += (
                    "- "
                    + x
                    + "\n"
                )



        prompt += (
            "\nTransferability:\n"
            + transfer["level"]
        )



        prompt += (
            "\n\nLLM Reasoning Guidance:\n"
        )


        for x in guidance["important_considerations"]:

            prompt += (
                "- "
                + x
                + "\n"
            )



        prompt += (
            "\nAvoid Literal Reproduction:\n"
            + str(
                guidance[
                    "avoid_literal_reproduction"
                ]
            )
        )


        prompt += (
            "\n\nGeneration Strategy:\n"
            + guidance["generation_strategy"]
        )


        prompt += "\n\n"



    return prompt




if __name__=="__main__":


    knowledge = load_knowledge(
        "torch.matmul"
    )


    print(
        knowledge_to_prompt(
            knowledge
        )
    )
